"""
Corrige en la base de datos las URLs de medios de destinos que apuntan a localhost.
Reemplaza por settings.BACKEND_URL (ej. https://tuki.cl) para hero_image, images y travel_guides.

Uso:
  python manage.py fix_destination_media_urls           # dry-run (solo muestra qué se cambiaría)
  python manage.py fix_destination_media_urls --apply   # aplica cambios en BD
"""
import re

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.landing_destinations.models import LandingDestination


def _replace_localhost(url):
    """Replace localhost/127.0.0.1 in URL with BACKEND_URL. Returns new URL or same if no change."""
    if not url or not isinstance(url, str):
        return url
    if "localhost" not in url and "127.0.0.1" not in url:
        return url
    base = getattr(settings, "BACKEND_URL", None)
    if not base:
        return url
    base = base.rstrip("/")
    for prefix in (
        "http://localhost:8000/",
        "http://localhost:8000",
        "http://localhost/",
        "http://localhost",
        "https://localhost:8000/",
        "https://localhost:8000",
        "https://localhost/",
        "https://localhost",
    ):
        if url.startswith(prefix):
            path = url[len(prefix) :].lstrip("/")
            return f"{base}/{path}" if path else base
    if "127.0.0.1" in url:
        path_match = re.search(r"https?://127\.0\.0\.1(?::\d+)?(/.+)?", url)
        if path_match:
            path = (path_match.group(1) or "").lstrip("/")
            return f"{base}/{path}" if path else base
    return url


class Command(BaseCommand):
    help = "Reemplaza URLs localhost en destinos (hero_image, images, travel_guides) por BACKEND_URL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplicar cambios en la BD. Por defecto solo dry-run.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        base = getattr(settings, "BACKEND_URL", None)
        if not base:
            self.stderr.write("BACKEND_URL no está definido en settings. No se puede reemplazar.")
            return
        self.stdout.write(f"Base URL: {base}")
        self.stdout.write("Modo: " + ("APLICAR cambios" if apply else "DRY-RUN (usa --apply para guardar)"))
        updated_count = 0
        for dest in LandingDestination.objects.all():
            updates = {}
            if dest.hero_image and ("localhost" in dest.hero_image or "127.0.0.1" in dest.hero_image):
                new_val = _replace_localhost(dest.hero_image)
                updates["hero_image"] = (dest.hero_image, new_val)
            if dest.images:
                new_list = []
                list_changed = False
                for u in dest.images:
                    if isinstance(u, str) and ("localhost" in u or "127.0.0.1" in u):
                        new_list.append(_replace_localhost(u))
                        list_changed = True
                    else:
                        new_list.append(u)
                if list_changed:
                    updates["images"] = (dest.images, new_list)
            if dest.travel_guides:
                new_guides = []
                guides_changed = False
                for g in dest.travel_guides:
                    if not isinstance(g, dict):
                        new_guides.append(g)
                        continue
                    img = g.get("image")
                    if isinstance(img, str) and ("localhost" in img or "127.0.0.1" in img):
                        new_guides.append({**g, "image": _replace_localhost(img)})
                        guides_changed = True
                    else:
                        new_guides.append(g)
                if guides_changed:
                    updates["travel_guides"] = (dest.travel_guides, new_guides)
            if not updates:
                continue
            self.stdout.write(f"  {dest.slug}: {list(updates.keys())}")
            for key, (old_val, new_val) in updates.items():
                self.stdout.write(f"    {key}: ... -> {str(new_val)[:80]}...")
            if apply:
                if "hero_image" in updates:
                    dest.hero_image = updates["hero_image"][1]
                if "images" in updates:
                    dest.images = updates["images"][1]
                if "travel_guides" in updates:
                    dest.travel_guides = updates["travel_guides"][1]
                dest.save()
                updated_count += 1
        if apply and updated_count:
            self.stdout.write(self.style.SUCCESS(f"Actualizados {updated_count} destino(s)."))
        elif apply:
            self.stdout.write("Nada que actualizar.")
        else:
            self.stdout.write("Ejecuta con --apply para guardar los cambios.")
