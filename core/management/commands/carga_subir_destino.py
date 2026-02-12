"""
Subir un destino (LandingDestination) desde una carpeta local con payload.json y opcional portada.
Pensado para ejecutarse dentro del contenedor en Dako: sin tokens, usando el primer superuser
como uploaded_by y scope=global para la imagen.
"""

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.files import File
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Crea LandingDestination y opcionalmente MediaAsset (portada) desde una carpeta con payload.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=str,
            help="Ruta a la carpeta que contiene payload.json y opcionalmente portada.png/jpg",
        )

    def handle(self, *args, **options):
        path = Path(options["path"]).resolve()
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

        hero_media_id = payload.get("hero_media_id")
        image_path = None
        for name in ("portada.png", "portada.jpg", "portada.jpeg", "portada.webp"):
            candidate = path / name
            if candidate.exists():
                image_path = candidate
                break
        if not image_path and not hero_media_id:
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                for p in path.glob(ext):
                    image_path = p
                    break
                if image_path:
                    break

        if image_path:
            from apps.media.models import MediaAsset

            content_type = "image/png"
            if image_path.suffix.lower() in (".jpg", ".jpeg"):
                content_type = "image/jpeg"
            elif image_path.suffix.lower() == ".webp":
                content_type = "image/webp"

            size_bytes = image_path.stat().st_size
            self.stdout.write(f"Creando MediaAsset (scope=global, uploaded_by=superuser) desde {image_path.name}")

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
            hero_media_id = str(asset.id)
            payload["hero_media_id"] = hero_media_id
            self.stdout.write(self.style.SUCCESS(f"  MediaAsset creado: {hero_media_id}"))

        from apps.landing_destinations.models import LandingDestination

        name = payload.get("name") or payload.get("title")
        slug = payload.get("slug")
        if not name or not slug:
            self.stderr.write(self.style.ERROR("payload.json debe tener name y slug"))
            return

        if LandingDestination.objects.filter(slug=slug).exists():
            self.stderr.write(self.style.ERROR(f"Ya existe un destino con slug: {slug}"))
            return

        dest = LandingDestination(
            name=name,
            slug=slug,
            country=payload.get("country", "Chile"),
            region=payload.get("region", ""),
            description=payload.get("description", ""),
            hero_image=payload.get("hero_image", "") or "",
            hero_media_id=hero_media_id,
            gallery_media_ids=payload.get("gallery_media_ids", []) or [],
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
