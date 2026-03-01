"""
Tareas Celery del core (uptime, etc.).
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Días de retención de heartbeats (limpieza automática)
UPTIME_HEARTBEAT_RETENTION_DAYS = 90


@shared_task(name="core.tasks.record_platform_uptime_heartbeat", ignore_result=True)
def record_platform_uptime_heartbeat():
    """
    Registra un heartbeat de plataforma en BD. Ejecutado cada minuto por Celery Beat.
    Los huecos entre heartbeats se interpretan como downtime.
    """
    try:
        from core.models import PlatformUptimeHeartbeat

        PlatformUptimeHeartbeat.objects.create(
            recorded_at=timezone.now(),
            source="celery",
        )
        logger.debug("Platform uptime heartbeat recorded")
    except Exception as e:
        logger.exception("Failed to record platform uptime heartbeat: %s", e)
        raise


@shared_task(name="core.tasks.cleanup_old_uptime_heartbeats", ignore_result=True)
def cleanup_old_uptime_heartbeats(days: int = None):
    """
    Elimina heartbeats más antiguos que N días. Ejecutado diariamente por Celery Beat.
    """
    from core.models import PlatformUptimeHeartbeat

    retain_days = days if days is not None else UPTIME_HEARTBEAT_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=retain_days)
    deleted, _ = PlatformUptimeHeartbeat.objects.filter(recorded_at__lt=cutoff).delete()
    if deleted:
        logger.info("Cleaned up %s old uptime heartbeats (older than %s)", deleted, cutoff.date())
