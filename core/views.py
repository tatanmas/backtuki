"""
Core API views (e.g. version, health).
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

# Timezone usada en todo el servidor (Santiago de Chile)
SERVER_TZ = ZoneInfo("America/Santiago")


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
        return Response({
            "version": version,
            "settings_module": os.environ.get("DJANGO_SETTINGS_MODULE", "unknown"),
            "backend_url": getattr(settings, "BACKEND_URL", None),
            "deployed_at": deployed_at_raw,
            "deployed_at_display": deployed_at_display,
            "timezone": "America/Santiago",
        })
