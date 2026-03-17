"""
Core API views (e.g. version, health, deploy-check).
"""
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

logger = logging.getLogger(__name__)

# Timezone usada en todo el servidor (Santiago de Chile)
SERVER_TZ = ZoneInfo("America/Santiago")

# Intervalo mínimo entre heartbeats desde health (segundos). ~1 por minuto para uptime real.
HEALTH_HEARTBEAT_THROTTLE_SECONDS = 55


def health_view(request):
    """
    Health check para load balancers / Cloud Run (GET /api/v1/health/).
    Responde 200 con 'ok'. Además registra un heartbeat de uptime (throttled)
    para que las métricas de uptime reflejen disponibilidad real aunque Celery
    Beat no esté escribiendo; el throttle evita saturar la BD.
    """
    try:
        from core.uptime_service import record_heartbeat_if_throttled
        record_heartbeat_if_throttled(
            min_interval_seconds=HEALTH_HEARTBEAT_THROTTLE_SECONDS,
            source="health",
        )
    except Exception:
        pass  # No fallar el health check si la BD falla
    return HttpResponse("ok", content_type="text/plain")


def _format_deployed_at(iso_value: str | None) -> str | None:
    """Format DEPLOYED_AT (ISO) to human-readable in America/Santiago."""
    if not iso_value or iso_value == "unknown":
        return None
    try:
        # Aceptar con o sin microsegundos / Z
        dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SERVER_TZ)
        else:
            dt = dt.astimezone(SERVER_TZ)
        return dt.strftime("%d/%m/%Y %H:%M:%S (Chile)")
    except (ValueError, TypeError):
        return iso_value


class VersionView(APIView):
    """
    GET /api/v1/version/
    Public endpoint to see which version is running and last deploy time (America/Santiago).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        version = os.environ.get("APP_VERSION", "dev")
        deployed_at_raw = os.environ.get("DEPLOYED_AT")
        deployed_at_display = _format_deployed_at(deployed_at_raw)
        payload = {
            "version": version,
            "deployed_at": deployed_at_raw,
            "deployed_at_display": deployed_at_display,
            "timezone": "America/Santiago",
        }
        # Expose internal details only in DEBUG to avoid information disclosure
        if getattr(settings, "DEBUG", False):
            payload["settings_module"] = os.environ.get("DJANGO_SETTINGS_MODULE", "unknown")
            payload["backend_url"] = getattr(settings, "BACKEND_URL", None)
        return Response(payload)


class DeployCheckView(APIView):
    """
    GET /api/v1/deploy-check/?key=SECRET
    Para que el script de deploy verifique si la versión se registró en BD (deploys_count, uptime).
    Solo responde si key coincide con DEPLOY_CHECK_SECRET en env.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        secret = os.environ.get("DEPLOY_CHECK_SECRET", "").strip()
        if not secret or request.GET.get("key") != secret:
            return Response(
                {"ok": False, "message": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )
        version = os.environ.get("APP_VERSION", "")
        deployed_at = os.environ.get("DEPLOYED_AT", "")
        uptime_seconds = None
        uptime_display = "—"
        try:
            from core.uptime import get_uptime_seconds
            from core.models import PlatformDeploy
            uptime_seconds = get_uptime_seconds()
            if uptime_seconds is not None and uptime_seconds >= 0:
                d = int(uptime_seconds) // 86400
                h = (int(uptime_seconds) % 86400) // 3600
                m = (int(uptime_seconds) % 3600) // 60
                s = int(uptime_seconds) % 60
                parts = []
                if d:
                    parts.append(f"{d}d")
                if h:
                    parts.append(f"{h}h")
                if m:
                    parts.append(f"{m}m")
                if not parts or s > 0:
                    parts.append(f"{s}s")
                uptime_display = " ".join(parts)
            deploys_count = PlatformDeploy.objects.count()
            last = PlatformDeploy.objects.order_by("-deployed_at").first()
            last_deploy_at = last.deployed_at.isoformat() if last else None
            last_version = last.version if last else None
        except Exception as e:
            logger.warning("deploy_check: %s", e)
            deploys_count = 0
            last_deploy_at = None
            last_version = None
        payload = {
            "ok": True,
            "env_version": version,
            "env_deployed_at": deployed_at,
            "deploys_count": deploys_count,
            "last_deploy_at": last_deploy_at,
            "last_deploy_version": last_version,
            "uptime_display": uptime_display,
            "uptime_seconds": uptime_seconds,
        }
        return Response(payload)
