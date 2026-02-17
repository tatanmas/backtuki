"""
Subir experiencias desde carpetas con dump.md + imagenes/ (ej. salida de scrapers TripAdvisor).
Pensado para ejecutarse dentro del contenedor en Dako: sin tokens, igual que carga_subir_destino.
Cada subcarpeta con dump.md se procesa: parseo → MediaAssets desde imagenes/ → Experience → opcionalmente vincular a destino.
Sale con código 1 en errores fatales para que el script shell detecte __FIN_ERROR__.
"""

import json
import re
import sys
from pathlib import Path
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.core.files import File
from django.utils.text import slugify
from django.db import transaction
from django.contrib.auth import get_user_model

User = get_user_model()


def _parse_dump_sections(content: str) -> dict:
    """Parsea dump.md por secciones ## Nombre."""
    sections = {}
    current = None
    buf = []
    for line in content.split("\n"):
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _parse_price(raw: str) -> Decimal | None:
    """Extrae número de precio desde texto (ej. 'Desde $140.975', '$140.975')."""
    if not raw:
        return None
    m = re.search(r"[\$€£]?\s*([\d.,]+)", str(raw).strip())
    if not m:
        return None
    num_str = m.group(1).replace(".", "").replace(",", ".")
    if "," in num_str:
        num_str = num_str.replace(",", "")
    try:
        return Decimal(num_str)
    except Exception:
        return None


def _parse_duration_minutes(raw: str) -> int | None:
    """'10 h' -> 600, '30 min' -> 30."""
    if not raw:
        return None
    raw = str(raw).strip()
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*h(?:\s|$)", raw, re.I)
    if m:
        return int(float(m.group(1).replace(",", ".")) * 60)
    m = re.match(r"^(\d+)\s*m(?:in|inutos)?(?:\s|$)", raw, re.I)
    if m:
        return int(m.group(1))
    return None


def _parse_list_section(text: str) -> list[str]:
    """Convierte texto de sección (líneas con '- item' o '• item') en lista de strings."""
    if not text or not text.strip():
        return []
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for prefix in ("- ", "• ", "* "):
            if line.startswith(prefix):
                line = line[len(prefix) :].strip()
                break
        if line:
            out.append(line[:500])
    return out[:50]


def parse_dump(dump_path: Path) -> dict:
    """Lee dump.md y devuelve dict con title, description, price, duration_minutes, included, not_included, itinerary, operator."""
    if not dump_path.exists():
        return {}
    content = dump_path.read_text(encoding="utf-8")
    sections = _parse_dump_sections(content)
    out = {
        "title": None,
        "description": None,
        "price": None,
        "duration_minutes": None,
        "operator": None,
        "included": [],
        "not_included": [],
        "itinerary": [],
    }
    if "Title" in sections:
        out["title"] = (sections["Title"] or "").strip() or None
    if "Description" in sections:
        out["description"] = (sections["Description"] or "").strip() or None
    if "Price" in sections:
        out["price"] = _parse_price(sections["Price"])
    if not out["price"]:
        m = re.search(r"desde\s+\$[\d.,]+|Desde\s+\$[\d.,]+", content, re.I)
        if m:
            out["price"] = _parse_price(m.group(0))
    if "Duration Minutes" in sections:
        out["duration_minutes"] = _parse_duration_minutes(sections["Duration Minutes"])
    if not out["duration_minutes"]:
        m = re.search(r"Duración:\s*(\d+)\s*h", content, re.I)
        if m:
            out["duration_minutes"] = int(m.group(1)) * 60
    if "Operator" in sections:
        out["operator"] = (sections["Operator"] or "").strip() or None
    if "Included" in sections:
        out["included"] = _parse_list_section(sections["Included"] or "")
    if "Not Included" in sections:
        out["not_included"] = _parse_list_section(sections["Not Included"] or "")
    if "Itinerary" in sections:
        out["itinerary"] = _parse_list_section(sections["Itinerary"] or "")
    return out


# Junk que el scraper de TripAdvisor mete en Description (eliminar para pulir el JSON)
_DESCRIPTION_JUNK = re.compile(
    r"América del Sur[A-Za-zÀ-ÿ\s]*San Pedro de Atacama|"
    r"Mira todas las cosas que hacer[^.\n]*|"
    r"Todas las Cosas que hacer[^.\n]*|"
    r"Compartir|Opinión|Guardar|Descripción general|Detalles|Itinerario|Operador|Opiniones|"
    r"Consultar disponibilidad|Leer más|desde\s+\$[\d.,]+|"
    r"Cancelación gratuita[^.]*\.|Reserva ahora y paga después[^.]*\.|El precio más bajo[^.]*\.|"
    r"Por qué a los viajeros les encanta|Edades:[^\n]+|Duración:\s*\d+\s*h|Horario de inicio[^\n]+|"
    r"Entrada para dispositivos[^\n]+|Guía en vivo:[^\n]+|Puntos destacados|Ver itinerario|"
    r"Qué está incluido|Qué esperar|Escrita el \d+ de [^\n]+|"
    r"^\s*\d+[,.]?\d*\s*$|^\s*\(\d+ opiniones\)\s*$|Recomendada por el \d+ %[^\n]*",
    re.I | re.MULTILINE,
)


def _clean_description(raw: str) -> str:
    """Limpia la descripción del dump: quita breadcrumbs, UI y deja el texto útil (Acerca de / párrafos reales)."""
    if not raw or not raw.strip():
        return ""
    text = _DESCRIPTION_JUNK.sub(" ", raw)
    # Buscar bloque "Acerca de" o el párrafo más largo que parezca descripción real (no reseñas)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and len(ln.strip()) > 20]
    best = []
    in_acerca = False
    for line in lines:
        if re.match(r"^Acerca de\s*$", line, re.I):
            in_acerca = True
            continue
        if in_acerca:
            if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+\s*$", line) or "Escrita el" in line:
                break
            best.append(line)
        elif not best and len(line) > 80 and not line.startswith("http"):
            best.append(line)
    out = " ".join(best).strip() if best else " ".join(lines[:3]).strip()
    out = re.sub(r"\s+", " ", out)[:8000]
    return out


def _humanize_folder_title(folder_name: str) -> str:
    """Extrae un título legible del nombre de carpeta (ej. AttractionProductReview-g303681-d23770376-Bike_Tour_to_Garganta... -> Bike Tour to Garganta del Diablo)."""
    # Quitar prefijos tipo AttractionProductReview-g303681-d25414775-
    s = re.sub(r"^AttractionProductReview-[a-z]?\d+-d?\d+-", "", folder_name, flags=re.I)
    s = s.replace("_", " ").replace("-", " ").strip()
    # Quitar sufijos truncados tipo "inclu" -> "includes bike" si aplica
    s = re.sub(r"\s+inclus?\s*$", " includes bike", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:255] if s else ""


def _make_slug_from_title(title: str, max_len: int = 47) -> str:
    """Slug legible para URL (solo desde el título, nunca desde la carpeta)."""
    s = slugify(title)
    return s[:max_len] if s else ""


def _adapt_itinerary_to_tuki(raw_items: list[str]) -> list[dict]:
    """Convierte lista de strings del dump a formato Tuki: [{title, time?, description?}, ...]."""
    out = []
    for i, item in enumerate(raw_items[:30]):
        s = (item or "").strip()
        if not s:
            continue
        # Si la línea empieza con hora tipo "06:00" o "9:00 - ", extraer time y resto como title
        m = re.match(r"^(\d{1,2}:\d{2})\s*[-–—]\s*(.+)$", s)
        if m:
            out.append({"time": m.group(1), "title": m.group(2).strip()[:300], "description": ""})
        else:
            out.append({"time": "", "title": s[:300], "description": ""})
    return out


class Command(BaseCommand):
    help = "Crea experiencias desde carpetas con dump.md e imagenes/ (ej. scraped/molantours). Ejecutar en Dako dentro del contenedor."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=str,
            help="Ruta a la carpeta que contiene subcarpetas (cada una con dump.md e imagenes/).",
        )
        parser.add_argument(
            "--organizer",
            type=str,
            required=True,
            help="Nombre o slug del organizador (ej. Molantur o molantours).",
        )
        parser.add_argument(
            "--destination-slug",
            type=str,
            default="",
            help="Slug del destino al que vincular las experiencias (ej. san-pedro-de-atacama).",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Crear experiencias como publicadas (status=published) para que se vean en la web.",
        )
        parser.add_argument(
            "--production-base-url",
            type=str,
            default="",
            help="URL base del frontend en producción (ej. https://tuki.cl). Si no se pasa, se usa FRONTEND_PRODUCTION_URL del settings o no se imprimen links.",
        )

    def handle(self, *args, **options):
        base_path = Path(options["path"]).resolve()
        organizer_arg = (options["organizer"] or "").strip()
        destination_slug = (options.get("destination_slug") or "").strip()
        publish = options.get("publish", False)
        production_base_url = (options.get("production_base_url") or "").strip()
        if not production_base_url:
            from django.conf import settings
            production_base_url = getattr(settings, "FRONTEND_PRODUCTION_URL", "") or ""

        if not base_path.is_dir():
            self.stderr.write(self.style.ERROR(f"No es un directorio: {base_path}"))
            sys.exit(1)

        from apps.organizers.models import Organizer
        from apps.media.models import MediaAsset
        from apps.experiences.models import Experience
        from api.v1.superadmin.serializers import JsonExperienceCreateSerializer
        from apps.landing_destinations.models import LandingDestination, LandingDestinationExperience
        from apps.media.models import MediaUsage
        from core.carga_helpers import get_or_create_tuki_organizer, normalize_operator_slug
        from core.models import Country as CoreCountry
        from django.contrib.contenttypes.models import ContentType

        organizer = None
        managed_operator_slug = ""
        if organizer_arg:
            organizer = (
                Organizer.objects.filter(slug__iexact=organizer_arg).first()
                or Organizer.objects.filter(name__icontains=organizer_arg).first()
            )
        if not organizer:
            organizer = get_or_create_tuki_organizer()
            managed_operator_slug = normalize_operator_slug(organizer_arg)
            self.stdout.write(
                self.style.WARNING(
                    f"Organizador '{organizer_arg}' no encontrado; usando Tuki y managed_operator_slug={managed_operator_slug!r}"
                )
            )
        if not organizer.has_experience_module:
            self.stderr.write(self.style.ERROR(f"El organizador '{organizer.name}' no tiene módulo de experiencias."))
            sys.exit(1)

        destination = None
        if destination_slug:
            destination = LandingDestination.objects.filter(slug=destination_slug).first()
            if not destination:
                self.stderr.write(self.style.WARNING(f"Destino con slug '{destination_slug}' no encontrado; no se vinculará a destino."))

        # País del destino para asignar a las experiencias (core.Country por nombre)
        destination_country = None
        if destination and getattr(destination, "country", None):
            dest_country_name = (destination.country or "").strip()
            if dest_country_name:
                destination_country = CoreCountry.objects.filter(
                    name__iexact=dest_country_name, is_active=True
                ).first() or CoreCountry.objects.filter(
                    name__icontains=dest_country_name, is_active=True
                ).first()

        superuser = User.objects.filter(is_superuser=True).first()
        created_ids = []
        created_slugs = []  # (id, slug) para links de producción

        subdirs = [
            d for d in base_path.iterdir()
            if d.is_dir() and (d / "dump.md").exists() and not d.name.startswith("test")
        ]
        if not subdirs:
            self.stderr.write(self.style.ERROR(f"No hay subcarpetas con dump.md en {base_path}"))
            sys.exit(1)

        for subdir in sorted(subdirs):
            dump_path = subdir / "dump.md"
            payload_path = subdir / "payload.json"
            imagenes_dir = subdir / "imagenes"

            # Si el agente (LLM) dejó payload.json adaptado, usarlo (mismo formato que destinos)
            if payload_path.exists():
                try:
                    with open(payload_path, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"  {subdir.name}: error leyendo payload.json: {e}"))
                    continue
                title = (payload.get("title") or "").strip()[:255]
                if not title:
                    self.stdout.write(self.style.WARNING(f"  Omitiendo {subdir.name}: payload.json sin title."))
                    continue
                description = (payload.get("description") or title)[:8000]
                short_description = (payload.get("short_description") or description.split(".")[0][:255])[:255]
                clean_slug = (payload.get("slug") or "").strip() or _make_slug_from_title(title)
                price = payload.get("price")
                if price is None:
                    price = Decimal("0")
                else:
                    price = Decimal(str(price))
                duration_minutes = payload.get("duration_minutes") or 600
                if duration_minutes and duration_minutes > 1440:
                    duration_minutes = 600
                included = payload.get("included") if isinstance(payload.get("included"), list) else []
                not_included = payload.get("not_included") if isinstance(payload.get("not_included"), list) else []
                raw_itinerary = payload.get("itinerary") if isinstance(payload.get("itinerary"), list) else []
                # Asegurar formato Tuki: list of {title, description?}
                itinerary = []
                for item in raw_itinerary[:30]:
                    if isinstance(item, dict) and item.get("title"):
                        itinerary.append({
                            "title": str(item["title"])[:300],
                            "description": str(item.get("description") or "")[:2000],
                            "time": str(item.get("time") or "")[:20],
                        })
                    elif isinstance(item, str) and item.strip():
                        itinerary.append({"title": item.strip()[:300], "description": "", "time": ""})
                experience_data_from_payload = {
                    "title": title,
                    "slug": clean_slug,
                    "description": description,
                    "short_description": short_description,
                    "status": "published" if publish else "draft",
                    "type": payload.get("type", "tour"),
                    "price": float(price),
                    "currency": (payload.get("currency") or "CLP")[:3],
                    "is_free_tour": bool(payload.get("is_free_tour", False)),
                    "credit_per_person": int(payload.get("credit_per_person", 5000)),
                    "sales_cutoff_hours": int(payload.get("sales_cutoff_hours", 2)),
                    "booking_horizon_days": int(payload.get("booking_horizon_days", 90)),
                    "included": [str(x)[:500] for x in included][:50],
                    "not_included": [str(x)[:500] for x in not_included][:50],
                    "itinerary": itinerary[:30],
                    "duration_minutes": duration_minutes,
                    "payment_model": payload.get("payment_model") or "full_upfront",
                }
            else:
                # Fallback: parsear dump.md (sin payload adaptado por el agente)
                data = parse_dump(dump_path)
                title = (data.get("title") or "").strip()
                if not title:
                    title = _humanize_folder_title(subdir.name)
                    if not title:
                        self.stdout.write(self.style.WARNING(f"  Omitiendo {subdir.name}: sin título en dump ni en nombre de carpeta."))
                        continue
                    self.stdout.write(self.style.WARNING(f"  Título desde carpeta: {title[:55]}"))
                title = title[:255]
                raw_desc = data.get("description") or ""
                description = _clean_description(raw_desc)
                if not description:
                    description = raw_desc[:2000].strip() or title
                description = description[:8000]
                short_description = (description.split(".")[0].strip() + "." if "." in description else description.split("\n")[0])[:255]
                if not short_description:
                    short_description = title[:255]
                clean_slug = _make_slug_from_title(title)
                price = data.get("price")
                if price is None:
                    price = Decimal("0")
                duration_minutes = data.get("duration_minutes") or 600
                if duration_minutes and duration_minutes > 1440:
                    duration_minutes = 600
                included = data.get("included") or []
                not_included = data.get("not_included") or []
                itinerary = _adapt_itinerary_to_tuki(data.get("itinerary") or [])
                experience_data_from_payload = {
                    "title": title,
                    "slug": clean_slug,
                    "description": description,
                    "short_description": short_description,
                    "status": "published" if publish else "draft",
                    "type": "tour",
                    "price": float(price),
                    "currency": "CLP",
                    "is_free_tour": False,
                    "credit_per_person": 5000,
                    "sales_cutoff_hours": 2,
                    "booking_horizon_days": 90,
                    "included": included,
                    "not_included": not_included,
                    "itinerary": itinerary,
                    "duration_minutes": duration_minutes,
                    "payment_model": "full_upfront",
                }

            image_urls = []
            assets_created = []  # MediaAssets subidos a la biblioteca (para registrar MediaUsage)
            if imagenes_dir.is_dir():
                image_files = sorted(imagenes_dir.glob("*"))
                image_files = [f for f in image_files if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")][:30]
                for img_path in image_files:
                    content_type = "image/jpeg"
                    if img_path.suffix.lower() in (".png",):
                        content_type = "image/png"
                    elif img_path.suffix.lower() in (".webp",):
                        content_type = "image/webp"
                    elif img_path.suffix.lower() in (".gif",):
                        content_type = "image/gif"
                    size_bytes = img_path.stat().st_size
                    asset = MediaAsset(
                        scope="organizer",
                        organizer=organizer,
                        uploaded_by=superuser,
                        original_filename=img_path.name,
                        content_type=content_type,
                        size_bytes=size_bytes,
                        sha256="",
                    )
                    with open(img_path, "rb") as f:
                        asset.file.save(img_path.name, File(f), save=True)
                    asset.save()
                    assets_created.append(asset)
                    url = asset.url
                    if url:
                        image_urls.append(url)
                    self.stdout.write(f"    MediaAsset: {img_path.name} -> {url[:50]}...")

            # Merge payload/dump data with imágenes subidas
            experience_data = {**experience_data_from_payload, "images": image_urls}
            if managed_operator_slug:
                experience_data["managed_operator_slug"] = managed_operator_slug
            serializer = JsonExperienceCreateSerializer(data=experience_data)
            if not serializer.is_valid():
                self.stderr.write(self.style.ERROR(f"  {subdir.name}: validación fallida: {serializer.errors}"))
                continue
            with transaction.atomic():
                validated = serializer.validated_data
                validated["organizer"] = organizer
                experience = serializer.create(validated)
                created_ids.append(str(experience.id))
                created_slugs.append((experience.id, experience.slug))
                if destination_country:
                    experience.country = destination_country
                    experience.save(update_fields=["country"])
                # Registrar en la biblioteca de medios: cada MediaAsset usado por esta experiencia (como en destino)
                if assets_created:
                    exp_content_type = ContentType.objects.get_for_model(Experience)
                    for asset in assets_created:
                        MediaUsage.objects.create(
                            asset=asset,
                            content_type=exp_content_type,
                            object_id=experience.id,
                            field_name="experience.images",
                        )
                    self.stdout.write(self.style.SUCCESS(f"    {len(assets_created)} foto(s) en biblioteca de medios (MediaUsage)"))
                self.stdout.write(self.style.SUCCESS(f"  Experiencia creada: {experience.title} (id={experience.id})"))

            if destination and experience:
                order = destination.destination_experiences.count()
                LandingDestinationExperience.objects.get_or_create(
                    destination=destination,
                    experience_id=experience.id,
                    defaults={"order": order},
                )
                self.stdout.write(self.style.SUCCESS(f"    Vinculada a destino: {destination.slug}"))

        self.stdout.write(self.style.SUCCESS(f"\nTotal: {len(created_ids)} experiencia(s) creada(s)."))
        if created_ids:
            self.stdout.write("IDs: " + ", ".join(created_ids))
        if production_base_url and created_slugs:
            base = production_base_url.rstrip("/")
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Links producción (para probar):"))
            for _id, slug in created_slugs:
                self.stdout.write(f"  {base}/experiences/{slug}")
