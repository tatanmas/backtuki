"""
Elimina heartbeats de uptime más antiguos que N días (evita crecimiento ilimitado de la tabla).
Uso: python manage.py cleanup_old_uptime_heartbeats [--days=90]
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import PlatformUptimeHeartbeat


class Command(BaseCommand):
    help = "Elimina heartbeats de uptime más antiguos que N días (default 90)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Mantener solo los últimos N días (default: 90).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo mostrar cuántos se eliminarían, sin borrar.",
        )

    def handle(self, *args, **options):
        days = max(1, options["days"])
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=days)
        qs = PlatformUptimeHeartbeat.objects.filter(recorded_at__lt=cutoff)
        count = qs.count()
        if dry_run:
            self.stdout.write(f"Se eliminarían {count} heartbeats anteriores a {cutoff.date()}.")
            return
        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Eliminados {deleted} heartbeats (anteriores a {cutoff.date()})."))
