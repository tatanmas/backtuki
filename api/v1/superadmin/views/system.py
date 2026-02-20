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


@api_view(['GET'])
@permission_classes([IsSuperUser])
def platform_status(request):
    """
    Platform status for SuperAdmin: uptime, version, deploy time, DB/Redis health.
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

        return Response({
            "ok": True,
            "version": version,
            "deployed_at": deployed_at,
            "uptime_seconds": uptime_seconds,
            "uptime_display": _format_uptime(uptime_seconds) if uptime_seconds is not None else "—",
            "database_ok": db_ok,
            "redis_ok": redis_ok,
        })
    except Exception as e:
        logger.exception("platform_status error")
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


