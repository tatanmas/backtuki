"""
SuperAdmin System Views
Endpoints para monitoreo del sistema.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
import logging

from core.models import CeleryTaskLog

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)

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


