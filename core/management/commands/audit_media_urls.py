"""
Audita y opcionalmente corrige referencias a localhost en medios.

- MediaAsset: las URLs se construyen en la API con BACKEND_URL cuando el request
  tiene host interno; no se guarda URL en BD (solo path del file). Este comando
  muestra cómo quedaría la URL con BACKEND_URL para verificar configuración.
- Accommodation.images: lista legacy de URLs; si alguna tiene localhost, se puede
  reemplazar por BACKEND_URL con --fix-accommodations.

Uso en Dako (docker exec):
  python manage.py audit_media_urls
  python manage.py audit_media_urls --fix-accommodations   # aplica corrección en Accommodation.images
"""
import re

from django.conf import settings
from django.core.management.base import BaseCommand


def _replace_localhost(url):
    """Reemplaza localhost/127.0.0.1 por BACKEND_URL."""
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
    help = "Audita URLs de medios (localhost vs BACKEND_URL) y opcionalmente corrige Accommodation.images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix-accommodations",
            action="store_true",
            help="Reemplazar localhost en Accommodation.images por BACKEND_URL y guardar.",
        )

    def handle(self, *args, **options):
        base = getattr(settings, "BACKEND_URL", None)
        self.stdout.write("=== Auditoría URLs de medios ===\n")
        self.stdout.write(f"  BACKEND_URL: {base or '(no definido)'}\n")

        # 1) MediaAsset: solo audit (las respuestas API ya usan BACKEND_URL en el serializer)
        try:
            from apps.media.models import MediaAsset

            total = MediaAsset.objects.filter(deleted_at__isnull=True).exclude(file="").count()
            self.stdout.write(f"  MediaAsset con file: {total}")
            sample = MediaAsset.objects.filter(deleted_at__isnull=True).exclude(file="").first()
            if sample and sample.file:
                raw_url = sample.file.url
                self.stdout.write(f"  Ejemplo file.url (storage): {raw_url[:90]}...")
                if base and ("localhost" in str(raw_url) or "127.0.0.1" in str(raw_url)):
                    from urllib.parse import urlparse

                    parsed = urlparse(str(raw_url))
                    path = parsed.path or ""
                    fixed = f"{base.rstrip('/')}{path}" if path.startswith("/") else f"{base}/{path}"
                    self.stdout.write(self.style.WARNING(f"  >>> En API se servirá como: {fixed[:90]}..."))
                elif base:
                    self.stdout.write(self.style.SUCCESS("  Las respuestas API usarán BACKEND_URL cuando el request sea interno."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  MediaAsset: {e}"))

        # 2) Accommodation.images (legacy list of URLs)
        try:
            from apps.accommodations.models import Accommodation

            accs_with_localhost = []
            for acc in Accommodation.objects.filter(deleted_at__isnull=True):
                images = acc.images or []
                for u in images:
                    if isinstance(u, str) and ("localhost" in u or "127.0.0.1" in u):
                        accs_with_localhost.append((acc, images))
                        break
            self.stdout.write(f"\n  Accommodation.images con localhost: {len(accs_with_localhost)}")
            for acc, images in accs_with_localhost[:5]:
                self.stdout.write(f"    - {acc.slug} ({acc.title[:40]}...)")
            if len(accs_with_localhost) > 5:
                self.stdout.write(f"    ... y {len(accs_with_localhost) - 5} más.")

            if options["fix_accommodations"] and accs_with_localhost and base:
                fixed_count = 0
                for acc, images in accs_with_localhost:
                    new_list = [_replace_localhost(u) if isinstance(u, str) else u for u in images]
                    acc.images = new_list
                    acc.save(update_fields=["images"])
                    fixed_count += 1
                self.stdout.write(self.style.SUCCESS(f"\n  Corregidos {fixed_count} alojamiento(s)."))
            elif options["fix_accommodations"] and accs_with_localhost and not base:
                self.stdout.write(self.style.ERROR("  Define BACKEND_URL para poder aplicar --fix-accommodations."))
            elif options["fix_accommodations"] and not accs_with_localhost:
                self.stdout.write("  Nada que corregir en Accommodation.images.")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Accommodation: {e}"))

        self.stdout.write("\n=== Fin auditoría ===")
