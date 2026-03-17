"""
Core application configuration.
"""

import logging
import os
from datetime import datetime

from django.apps import AppConfig
from django.utils import timezone

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Core"

    def ready(self):
        from core.uptime import set_start_time
        set_start_time()
        _record_deploy_if_env_set()


def _record_deploy_if_env_set():
    """
    Si DEPLOYED_AT está definido, registra un PlatformDeploy al arrancar.
    Evita duplicados: no inserta si ya existe un deploy en el mismo minuto.
    """
    deployed_at_str = os.environ.get("DEPLOYED_AT")
    if not deployed_at_str or not deployed_at_str.strip():
        return
    try:
        raw = deployed_at_str.strip().replace("Z", "+00:00")
        deployed_at = datetime.fromisoformat(raw)
        if timezone.is_naive(deployed_at):
            deployed_at = timezone.make_aware(deployed_at)
    except Exception as e:
        logger.warning("Could not parse DEPLOYED_AT=%r: %s", deployed_at_str[:50], e)
        return
    version = (os.environ.get("APP_VERSION") or "").strip() or None
    try:
        from core.models import PlatformDeploy
        # Evitar duplicado: mismo minuto (varios workers pueden arrancar a la vez)
        window_start = deployed_at.replace(second=0, microsecond=0)
        window_end = window_start + timezone.timedelta(minutes=1)
        if PlatformDeploy.objects.filter(
            deployed_at__gte=window_start,
            deployed_at__lt=window_end,
        ).exists():
            return
        PlatformDeploy.objects.create(
            deployed_at=deployed_at,
            version=version or "",
            source="startup",
        )
        logger.info("Recorded platform deploy: version=%s at %s", version, deployed_at)
    except Exception as e:
        logger.warning("Could not record platform deploy: %s", e)

