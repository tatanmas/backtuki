"""
Registra un heartbeat de uptime en BD (para cron sin Celery o backfill).
Uso: python manage.py record_platform_heartbeat
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import PlatformUptimeHeartbeat


class Command(BaseCommand):
    help = "Registra un heartbeat de plataforma en BD (uptime)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            default="management_command",
            help="Origen del heartbeat (default: management_command).",
        )

    def handle(self, *args, **options):
        source = options["source"]
        PlatformUptimeHeartbeat.objects.create(recorded_at=timezone.now(), source=source)
        self.stdout.write(self.style.SUCCESS("Heartbeat registrado."))
