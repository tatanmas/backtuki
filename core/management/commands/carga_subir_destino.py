"""
Subir un destino (LandingDestination) desde una carpeta local con payload.json y opcional portada/galería.
Pensado para ejecutarse dentro del contenedor en Dako: sin tokens, usando el primer superuser
como uploaded_by y scope=global para las imágenes.

Modo crear: crea destino nuevo; si ya existe el slug, falla.
Modo --update: actualiza destino existente por slug; sube todas las imágenes de la carpeta
  (portada.* = hero, el resto o todas = galería) a la biblioteca de medios y actualiza hero_media_id y gallery_media_ids.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.files import File
from django.contrib.auth import get_user_model

User = get_user_model()

# Extensiones de imagen que se suben a la biblioteca
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
IMAGE_GLOB = ("*.png", "*.jpg", "*.jpeg", "*.webp")
PORTADA_NAMES = ("portada.png", "portada.jpg", "portada.jpeg", "portada.webp")


def _content_type(path):
    suf = path.suffix.lower()
    if suf in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suf == ".webp":
        return "image/webp"
    return "image/png"


def _collect_image_paths(path):
    """Devuelve lista ordenada: primero portada si existe, luego resto de imágenes por nombre."""
    portada = None
    for name in PORTADA_NAMES:
        candidate = path / name
        if candidate.exists():
            portada = candidate
            break
    others = []
    for ext in IMAGE_GLOB:
        for p in sorted(path.glob(ext)):
            if p.is_file() and (not portada or p != portada):
                others.append(p)
    if portada:
        return [portada] + others
    return others


def _create_media_assets(paths, superuser, stdout, style):
    """Crea un MediaAsset por cada path; devuelve lista de UUIDs (strings)."""
    from apps.media.models import MediaAsset

    ids = []
    for image_path in paths:
        content_type = _content_type(image_path)
        size_bytes = image_path.stat().st_size
        stdout.write(f"Creando MediaAsset (scope=global) desde {image_path.name}")
        asset = MediaAsset(
            scope="global",
            organizer=None,
            uploaded_by=superuser,
            original_filename=image_path.name,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256="",
        )
        with open(image_path, "rb") as f:
            asset.file.save(image_path.name, File(f), save=True)
        asset.save()
        ids.append(str(asset.id))
        stdout.write(style.SUCCESS(f"  MediaAsset creado: {asset.id}"))
    return ids


class Command(BaseCommand):
    help = "Crea o actualiza LandingDestination y sube imágenes (portada + galería) desde una carpeta con payload.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=str,
            help="Ruta a la carpeta que contiene payload.json y opcionalmente portada.png/jpg y más imágenes",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Actualizar destino existente por slug; sube imágenes de la carpeta a la biblioteca y actualiza hero y galería",
        )

    def handle(self, *args, **options):
        path = Path(options["path"]).resolve()
        do_update = options.get("update", False)

        if not path.is_dir():
            self.stderr.write(self.style.ERROR(f"No es un directorio: {path}"))
            return

        payload_file = path / "payload.json"
        if not payload_file.exists():
            self.stderr.write(self.style.ERROR(f"No existe {payload_file}"))
            return

        with open(payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)

        superuser = User.objects.filter(is_superuser=True).first()
        if not superuser:
            self.stderr.write(self.style.ERROR("No hay ningún superuser en la BD"))
            return

        from apps.landing_destinations.models import LandingDestination

        name = payload.get("name") or payload.get("title")
        slug = payload.get("slug")
        if not name or not slug:
            self.stderr.write(self.style.ERROR("payload.json debe tener name y slug"))
            return

        # Recoger todas las imágenes de la carpeta (portada primero, luego resto)
        image_paths = _collect_image_paths(path)
        hero_media_id = payload.get("hero_media_id")
        gallery_media_ids = list(payload.get("gallery_media_ids") or [])

        if image_paths:
            ids = _create_media_assets(image_paths, superuser, self.stdout, self.style)
            hero_media_id = ids[0]
            gallery_media_ids = ids  # hero es el primero, el resto también en galería
            payload["hero_media_id"] = hero_media_id
            payload["gallery_media_ids"] = gallery_media_ids

        if do_update:
            dest = LandingDestination.objects.filter(slug=slug).first()
            if not dest:
                self.stderr.write(self.style.ERROR(f"No existe un destino con slug: {slug}. Crea primero sin --update."))
                return
            dest.name = name
            dest.country = payload.get("country", "Chile")
            dest.region = payload.get("region", "")
            dest.description = payload.get("description", "")
            dest.hero_image = payload.get("hero_image", "") or ""
            # Solo actualizar media si subimos imágenes nuevas; si no hay archivos, conservar las actuales
            if image_paths:
                dest.hero_media_id = hero_media_id
                dest.gallery_media_ids = gallery_media_ids
            dest.latitude = payload.get("latitude")
            dest.longitude = payload.get("longitude")
            dest.is_active = payload.get("is_active", True)
            dest.images = payload.get("images", []) or []
            dest.travel_guides = payload.get("travel_guides", []) or []
            dest.transportation = payload.get("transportation", []) or []
            dest.accommodation_ids = payload.get("accommodation_ids", []) or []
            dest.featured_type = payload.get("featured_type")
            dest.featured_id = payload.get("featured_id")
            dest.save()
            self.stdout.write(self.style.SUCCESS(f"Destino actualizado: {dest.name} (id={dest.id}, slug={dest.slug})"))
            return

        if LandingDestination.objects.filter(slug=slug).exists():
            self.stderr.write(
                self.style.ERROR(f"Ya existe un destino con slug: {slug}. Usa --update para subir fotos y actualizar.")
            )
            return

        dest = LandingDestination(
            name=name,
            slug=slug,
            country=payload.get("country", "Chile"),
            region=payload.get("region", ""),
            description=payload.get("description", ""),
            hero_image=payload.get("hero_image", "") or "",
            hero_media_id=hero_media_id,
            gallery_media_ids=gallery_media_ids,
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            is_active=payload.get("is_active", True),
            images=payload.get("images", []) or [],
            travel_guides=payload.get("travel_guides", []) or [],
            transportation=payload.get("transportation", []) or [],
            accommodation_ids=payload.get("accommodation_ids", []) or [],
            featured_type=payload.get("featured_type"),
            featured_id=payload.get("featured_id"),
        )
        dest.save()
        self.stdout.write(self.style.SUCCESS(f"Destino creado: {dest.name} (id={dest.id}, slug={dest.slug})"))
