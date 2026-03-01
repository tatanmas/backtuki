"""
SuperAdmin System Views
Endpoints para monitoreo del sistema (Celery, platform status, uptime).
"""

import os
import logging
from datetime import timedelta

from django.utils import timezone
from django.db.models import Count

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from core.models import CeleryTaskLog
from core.uptime import get_uptime_seconds
from core.uptime_service import (
    get_uptime_report,
    get_last_heartbeat,
    get_current_run_start,
    DOWNTIME_GAP_SECONDS,
)

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


def _format_uptime(seconds: float) -> str:
    """Format seconds to human-readable uptime (e.g. '2d 5h 12m')."""
    if seconds is None or seconds < 0:
        return "—"
    d = int(seconds) // 86400
    h = (int(seconds) % 86400) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if not parts or s > 0:
        parts.append(f"{s}s")
    return " ".join(parts)


def _platform_uptime_payload():
    """Datos de uptime basados en heartbeats en BD (opcional; no falla si no hay datos)."""
    try:
        last_hb = get_last_heartbeat()
        consider_down_after = timedelta(seconds=DOWNTIME_GAP_SECONDS)
        is_currently_up = last_hb is not None and (timezone.now() - last_hb) <= consider_down_after
        current_run_start = get_current_run_start()
        current_run_seconds = (timezone.now() - current_run_start).total_seconds() if current_run_start else None

        report_24h = get_uptime_report(period_hours=24)
        report_7d = get_uptime_report(period_hours=24 * 7)
        report_30d = get_uptime_report(period_hours=24 * 30)

        return {
            "uptime_from_db": True,
            "last_heartbeat_at": last_hb.isoformat() if last_hb else None,
            "is_currently_up": is_currently_up,
            "current_run_started_at": current_run_start.isoformat() if current_run_start else None,
            "current_run_seconds": round(current_run_seconds, 1) if current_run_seconds is not None else None,
            "current_run_display": _format_uptime(current_run_seconds) if current_run_seconds is not None else "—",
            "uptime_percent_24h": round(report_24h.uptime_percent, 2),
            "uptime_percent_7d": round(report_7d.uptime_percent, 2),
            "uptime_percent_30d": round(report_30d.uptime_percent, 2),
        }
    except Exception as e:
        logger.warning("platform_uptime_payload failed: %s", e)
        return {
            "uptime_from_db": False,
            "last_heartbeat_at": None,
            "is_currently_up": None,
            "current_run_started_at": None,
            "current_run_seconds": None,
            "current_run_display": "—",
            "uptime_percent_24h": None,
            "uptime_percent_7d": None,
            "uptime_percent_30d": None,
        }


@api_view(['GET'])
@permission_classes([IsSuperUser])
def platform_status(request):
    """
    Platform status for SuperAdmin: uptime, version, deploy time, DB/Redis health.
    Incluye uptime persistido en BD (%, último heartbeat, tramo actual).
    GET /api/v1/superadmin/platform-status/
    """
    try:
        uptime_seconds = get_uptime_seconds()
        version = os.environ.get("APP_VERSION", "dev")
        deployed_at = os.environ.get("DEPLOYED_AT")

        # Optional: DB and Redis health (don't fail the whole response)
        db_ok = None
        redis_ok = None
        try:
            from django.db import connection
            connection.ensure_connection()
            db_ok = True
        except Exception:
            db_ok = False
        try:
            from django.core.cache import cache
            cache.set("platform_status_ping", 1, 5)
            redis_ok = cache.get("platform_status_ping") == 1
        except Exception:
            redis_ok = False

        payload = {
            "ok": True,
            "version": version,
            "deployed_at": deployed_at,
            "uptime_seconds": uptime_seconds,
            "uptime_display": _format_uptime(uptime_seconds) if uptime_seconds is not None else "—",
            "database_ok": db_ok,
            "redis_ok": redis_ok,
        }
        payload.update(_platform_uptime_payload())
        return Response(payload)
    except Exception as e:
        logger.exception("platform_status error")
        return Response(
            {"ok": False, "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([IsSuperUser])
def platform_uptime_report(request):
    """
    Reporte de uptime: % por periodo, incidentes de caída (cuándo no estuvo arriba).
    GET /api/v1/superadmin/platform-uptime-report/?hours=168
    Query: hours (default 168 = 7 días)
    """
    try:
        hours = int(request.GET.get("hours", 168))
        hours = max(1, min(hours, 24 * 90))  # entre 1h y 90 días
        report = get_uptime_report(period_hours=hours)

        incidents_payload = [
            {
                "started_at": inc.started_at.isoformat(),
                "ended_at": inc.ended_at.isoformat(),
                "duration_seconds": round(inc.duration_seconds, 1),
                "duration_display": _format_uptime(inc.duration_seconds),
            }
            for inc in report.incidents
        ]

        return Response({
            "ok": True,
            "period_hours": hours,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "total_seconds": report.total_seconds,
            "uptime_seconds": report.uptime_seconds,
            "downtime_seconds": report.downtime_seconds,
            "uptime_percent": round(report.uptime_percent, 2),
            "last_heartbeat_at": report.last_heartbeat_at.isoformat() if report.last_heartbeat_at else None,
            "is_currently_up": report.is_currently_up,
            "current_run_started_at": report.current_run_started_at.isoformat() if report.current_run_started_at else None,
            "current_run_seconds": round(report.current_run_seconds, 1) if report.current_run_seconds is not None else None,
            "incidents": incidents_payload,
            "incidents_count": len(incidents_payload),
        })
    except Exception as e:
        logger.exception("platform_uptime_report error")
        return Response(
            {"ok": False, "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def celery_tasks_list(request):
    """
    Get list of Celery task logs.
    
    Supports filtering by:
    - task_name
    - status
    - date range
    """
    try:
        from core.models import CeleryTaskLog
        from datetime import timedelta
        
        # Get filters
        task_name = request.GET.get('task_name')
        task_status = request.GET.get('status')
        days = int(request.GET.get('days', 7))
        limit = int(request.GET.get('limit', 50))
        
        start_date = timezone.now() - timedelta(days=days)
        
        # Build query
        query = CeleryTaskLog.objects.filter(created_at__gte=start_date)
        
        if task_name:
            query = query.filter(task_name__icontains=task_name)
        
        if task_status:
            query = query.filter(status=task_status)
        
        # Get logs
        logs = query.select_related('flow', 'order', 'user').order_by('-created_at')[:limit]
        
        # Get counts by status
        status_counts = CeleryTaskLog.objects.filter(
            created_at__gte=start_date
        ).values('status').annotate(count=Count('id'))
        
        return Response({
            'success': True,
            'logs': [{
                'id': str(log.id),
                'task_id': log.task_id,
                'task_name': log.task_name,
                'status': log.status,
                'queue': log.queue,
                'created_at': log.created_at.isoformat(),
                'duration_ms': log.duration_ms,
                'error': log.error[:200] if log.error else None,  # Truncate error
                'flow_id': str(log.flow.id) if log.flow else None,
                'order_id': str(log.order.id) if log.order else None,
                'order_number': log.order.order_number if log.order else None
            } for log in logs],
            'status_counts': {item['status']: item['count'] for item in status_counts},
            'total': query.count()
        })
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting celery tasks: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting celery tasks: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


