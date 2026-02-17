"""
Subir un alojamiento desde una carpeta con payload.json y fotos/ o imagenes/.
Mismo patrón que carga_subir_destino y carga_subir_experiencias: ejecutar dentro del
contenedor en Dako, sin tokens; usa superuser para MediaAsset y get_or_create_tuki_organizer
si no se indica organizador.
Sale con código 1 en errores fatales para que el script shell detecte __FIN_ERROR__.
"""

import json
import sys
from pathlib import Path
from decimal import Decimal
from datetime import date

from django.core.management.base import BaseCommand
from django.core.files import File
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils.text import slugify

User = get_user_model()


def _parse_review_date(value):
    """Convierte string 'YYYY-MM-DD' o 'mes de YYYY' en date o None."""
    if value is None:
        return None
    if hasattr(value, "year"):
        return value
    s = (value or "").strip()
    if not s:
        return None
    # ISO
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
        except (ValueError, TypeError):
            pass
    # "febrero de 2025" -> aprox 15 de ese mes
    months_es = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    s_lower = s.lower()
    for name, month in months_es.items():
        if name in s_lower and "de " in s_lower:
            try:
                year = int(s_lower.split("de ")[-1].strip()[:4])
                return date(year, month, 15)
            except (ValueError, TypeError, IndexError):
                pass
    return None


class Command(BaseCommand):
    help = (
        "Crea un Accommodation (y reseñas) desde una carpeta con payload.json y fotos/ o imagenes/. "
        "Para ejecutar en Dako dentro del contenedor (sin tokens)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=str,
            help="Ruta a la carpeta que contiene payload.json y opcionalmente fotos/ o imagenes/.",
        )
        parser.add_argument(
            "--organizer",
            type=str,
            default="",
            help="Nombre o slug del organizador (ej. Tuki). Si no existe, se usa Tuki y managed_operator_slug.",
        )
        parser.add_argument(
            "--destination-slug",
            type=str,
            default="",
            help="Slug del destino al que vincular el alojamiento (se agrega a accommodation_ids).",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Crear alojamiento como publicado (status=published).",
        )
        parser.add_argument(
            "--production-base-url",
            type=str,
            default="",
            help="URL base del frontend en producción para imprimir link (ej. https://tuki.cl).",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Si ya existe un alojamiento con el mismo slug, actualizarlo en lugar de fallar.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"]).resolve()
        organizer_arg = (options.get("organizer") or "").strip()
        destination_slug = (options.get("destination_slug") or "").strip()
        publish = options.get("publish", False)
        production_base_url = (options.get("production_base_url") or "").strip()
        update = options.get("update", False)

        if not path.is_dir():
            self.stderr.write(self.style.ERROR(f"No es un directorio: {path}"))
            sys.exit(1)

        payload_file = path / "payload.json"
        if not payload_file.exists():
            self.stderr.write(self.style.ERROR(f"No existe {payload_file}"))
            sys.exit(1)

        try:
            with open(payload_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error leyendo payload.json: {e}"))
            sys.exit(1)

        title = (payload.get("title") or "").strip()[:255]
        if not title:
            self.stderr.write(self.style.ERROR("payload.json debe tener title"))
            sys.exit(1)

        slug_raw = (payload.get("slug") or "").strip()
        clean_slug = slug_raw or slugify(title)[:255]
        if not clean_slug:
            clean_slug = slugify(title)[:255] or "alojamiento"

        self.stdout.write(f"  Ruta recibida: {path}")
        self.stdout.write(f"  Slug alojamiento: {clean_slug}")

        from apps.accommodations.models import Accommodation, AccommodationReview
        from apps.organizers.models import Organizer
        from apps.media.models import MediaAsset
        from apps.landing_destinations.models import LandingDestination
        from core.carga_helpers import get_or_create_tuki_organizer

        superuser = User.objects.filter(is_superuser=True).first()
        if not superuser:
            self.stderr.write(self.style.ERROR("No hay ningún superuser en la BD"))
            sys.exit(1)

        organizer = None
        if organizer_arg:
            organizer = (
                Organizer.objects.filter(slug__iexact=organizer_arg).first()
                or Organizer.objects.filter(name__icontains=organizer_arg).first()
            )
        if not organizer:
            organizer = get_or_create_tuki_organizer()
            self.stdout.write(
                self.style.WARNING(
                    f"Organizador '{organizer_arg or '(vacío)'}' no encontrado; usando Tuki."
                )
            )

        # Imágenes: fotos/ o imagenes/
        # Se renombran con prefijo {slug}-{índice} para que cada alojamiento tenga nombres únicos
        # y no se mezclen fotos entre cabañas (ej. rocas-de-elki-00.avif, rocas-de-elki-terral-00.avif).
        imagenes_dir = path / "fotos"
        if not imagenes_dir.is_dir():
            imagenes_dir = path / "imagenes"
        image_urls = []
        gallery_media_ids = []
        if imagenes_dir.is_dir():
            image_files = sorted(imagenes_dir.glob("*"))
            image_files = [
                f for f in image_files
                if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")
            ][:30]
            self.stdout.write(f"  Fotos en {imagenes_dir} ({len(image_files)} archivos) → subiendo como «{clean_slug}-NN»")
            for i, img_path in enumerate(image_files):
                content_type = "image/jpeg"
                if img_path.suffix.lower() == ".png":
                    content_type = "image/png"
                elif img_path.suffix.lower() == ".webp":
                    content_type = "image/webp"
                elif img_path.suffix.lower() == ".gif":
                    content_type = "image/gif"
                elif img_path.suffix.lower() == ".avif":
                    content_type = "image/avif"
                size_bytes = img_path.stat().st_size
                # Nombre único por alojamiento: slug + índice + extensión (evita mezcla entre cabañas)
                safe_ext = img_path.suffix.lower()
                unique_name = f"{clean_slug}-{i:02d}{safe_ext}"
                asset = MediaAsset(
                    scope="organizer",
                    organizer=organizer,
                    uploaded_by=superuser,
                    original_filename=unique_name,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    sha256="",
                )
                with open(img_path, "rb") as f:
                    asset.file.save(unique_name, File(f), save=True)
                asset.save()
                gallery_media_ids.append(str(asset.id))
                if asset.url:
                    image_urls.append(asset.url)
                self.stdout.write(f"  MediaAsset: {img_path.name} → {unique_name}")

        # Payload -> campos del modelo
        description = (payload.get("description") or "")[:8000]
        short_description = (payload.get("short_description") or description.split(".")[0] or "")[:500]
        location_name = (payload.get("location_name") or payload.get("location", {}).get("name") or "")[:255]
        location_address = (payload.get("location_address") or payload.get("location", {}).get("address") or "")[:2000]
        loc = payload.get("location") or {}
        lat = payload.get("latitude") or (loc.get("coordinates") or {}).get("lat")
        lon = payload.get("longitude") or (loc.get("coordinates") or {}).get("lng")
        country = (payload.get("country") or "Chile")[:255]
        city = (payload.get("city") or "")[:255]
        guests = max(1, int(payload.get("guests") or 2))
        bedrooms = max(0, int(payload.get("bedrooms") or 1))
        bathrooms = max(0, int(payload.get("bathrooms") or 1))
        beds = payload.get("beds")
        if beds is not None:
            beds = max(0, int(beds))
        price = Decimal(str(payload.get("price") or 0))
        currency = (payload.get("currency") or "CLP")[:3]
        amenities = [str(x)[:500] for x in (payload.get("amenities") or [])][:100]
        not_amenities = [str(x)[:500] for x in (payload.get("not_amenities") or [])][:50]
        property_type = (payload.get("property_type") or "cabin")[:20]
        if property_type not in ("cabin", "house", "apartment", "hotel", "hostel", "villa", "other"):
            property_type = "cabin"
        rating_avg = payload.get("rating_avg") or payload.get("rating")
        if rating_avg is not None:
            rating_avg = Decimal(str(rating_avg))
        review_count = int(payload.get("review_count") or 0)
        reviews_data = payload.get("reviews") or []
        if isinstance(reviews_data, list):
            review_count = max(review_count, len(reviews_data))

        acc = Accommodation.objects.filter(slug=clean_slug).first()
        if acc and not update:
            self.stderr.write(self.style.ERROR(f"Ya existe un alojamiento con slug: {clean_slug}. Usa --update para actualizar."))
            sys.exit(1)

        is_new = acc is None
        with transaction.atomic():
            if acc:
                acc.title = title
                acc.description = description
                acc.short_description = short_description
                acc.status = "published" if publish else acc.status
                acc.property_type = property_type
                acc.location_name = location_name
                acc.location_address = location_address
                acc.latitude = float(lat) if lat is not None else None
                acc.longitude = float(lon) if lon is not None else None
                acc.country = country
                acc.city = city
                acc.guests = guests
                acc.bedrooms = bedrooms
                acc.bathrooms = bathrooms
                acc.beds = beds
                acc.price = price
                acc.currency = currency
                acc.amenities = amenities
                acc.not_amenities = not_amenities
                acc.images = image_urls
                acc.gallery_media_ids = gallery_media_ids
                acc.rating_avg = rating_avg
                acc.review_count = review_count
                acc.save()
                self.stdout.write(self.style.SUCCESS(f"Alojamiento actualizado: {acc.title} (id={acc.id}, slug={acc.slug})"))
            else:
                acc = Accommodation(
                    title=title,
                    slug=clean_slug,
                    description=description,
                    short_description=short_description,
                    status="published" if publish else "draft",
                    property_type=property_type,
                    organizer=organizer,
                    location_name=location_name,
                    location_address=location_address,
                    latitude=float(lat) if lat is not None else None,
                    longitude=float(lon) if lon is not None else None,
                    country=country,
                    city=city,
                    guests=guests,
                    bedrooms=bedrooms,
                    bathrooms=bathrooms,
                    beds=beds,
                    price=price,
                    currency=currency,
                    amenities=amenities,
                    not_amenities=not_amenities,
                    images=image_urls,
                    gallery_media_ids=gallery_media_ids,
                    rating_avg=rating_avg,
                    review_count=review_count,
                )
                acc.save()
                self.stdout.write(self.style.SUCCESS(f"Alojamiento creado: {acc.title} (id={acc.id}, slug={acc.slug})"))

            # Reseñas solo al crear (con --update no se vuelven a crear)
            if is_new:
                created_count = 0
                for i, r in enumerate(reviews_data[:50]):
                    if not isinstance(r, dict):
                        continue
                    author_name = (r.get("author_name") or "").strip()[:255]
                    if not author_name:
                        continue
                    author_location = (r.get("author_location") or "")[:255]
                    rating = max(1, min(5, int(r.get("rating") or 5)))
                    text = (r.get("text") or "")[:5000]
                    review_date = _parse_review_date(r.get("review_date"))
                    stay_type = (r.get("stay_type") or "")[:100]
                    host_reply = (r.get("host_reply") or "")[:2000]
                    AccommodationReview.objects.create(
                        accommodation=acc,
                        author_name=author_name,
                        author_location=author_location,
                        rating=rating,
                        text=text,
                        review_date=review_date,
                        stay_type=stay_type,
                        host_reply=host_reply,
                    )
                    created_count += 1
                if created_count:
                    self.stdout.write(self.style.SUCCESS(f"  {created_count} reseña(s) creada(s)."))

            if destination_slug:
                dest = LandingDestination.objects.filter(slug=destination_slug).first()
                if dest:
                    ids = list(dest.accommodation_ids or [])
                    if str(acc.id) not in ids:
                        ids.append(str(acc.id))
                        dest.accommodation_ids = ids
                        dest.save(update_fields=["accommodation_ids"])
                    self.stdout.write(self.style.SUCCESS(f"  Vinculado a destino: {destination_slug}"))
                else:
                    self.stdout.write(self.style.WARNING(f"  Destino con slug '{destination_slug}' no encontrado."))

        if production_base_url:
            base = production_base_url.rstrip("/")
            self.stdout.write(self.style.SUCCESS(f"Link producción: {base}/alojamientos/{acc.slug}"))
