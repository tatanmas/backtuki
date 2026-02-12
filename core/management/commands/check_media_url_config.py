"""
Diagnóstico: qué URL base usa el backend para medios (destinos, biblioteca).
Ejecutar en el servidor (SSH + docker exec) para ver el estado real antes de asumir la causa.

Uso:
  python manage.py check_media_url_config
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Muestra BACKEND_URL, settings cargados y una URL de ejemplo para medios (diagnóstico)."

    def handle(self, *args, **options):
        self.stdout.write("=== Diagnóstico URLs de medios (destinos / biblioteca) ===\n")

        # 1) Env en el proceso (lo que ve el contenedor)
        backend_url_env = os.environ.get("BACKEND_URL", "")
        self.stdout.write(f"  ENV BACKEND_URL (en proceso): {repr(backend_url_env)}")

        # 2) Lo que ve Django
        backend_url_settings = getattr(settings, "BACKEND_URL", None)
        self.stdout.write(f"  settings.BACKEND_URL:            {repr(backend_url_settings)}")

        # 3) Settings module cargado
        self.stdout.write(f"  DJANGO_SETTINGS_MODULE:         {os.environ.get('DJANGO_SETTINGS_MODULE', '?')}")

        # 4) DEBUG
        self.stdout.write(f"  settings.DEBUG:                 {getattr(settings, 'DEBUG', None)}")

        # 5) ALLOWED_HOSTS (primeros 3)
        allowed = getattr(settings, "ALLOWED_HOSTS", [])
        if isinstance(allowed, (list, tuple)):
            preview = list(allowed)[:3]
        else:
            preview = [str(allowed)[:80]]
        self.stdout.write(f"  settings.ALLOWED_HOSTS (preview): {preview}")

        # 6) Una URL de ejemplo desde el modelo (como la que usa destino/biblioteca)
        try:
            from apps.media.models import MediaAsset

            sample = MediaAsset.objects.filter(deleted_at__isnull=True).filter(file__isnull=False).first()
            if sample:
                example_url = sample.url
                self.stdout.write(f"  MediaAsset.url (ejemplo):         {example_url}")
                if example_url and "localhost" in example_url:
                    self.stdout.write(self.style.WARNING("  >>> Problema: la URL de ejemplo contiene 'localhost'."))
            else:
                self.stdout.write("  MediaAsset.url (ejemplo):         (no hay assets para probar)")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  MediaAsset.url (ejemplo): Error - {e}"))

        self.stdout.write("\n=== Fin diagnóstico ===")
