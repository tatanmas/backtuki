"""
SuperAdmin Platform Flow Monitoring Views
Endpoints para monitoreo de flows de la plataforma.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
import logging
import concurrent.futures
from threading import Lock

from apps.events.models import Order, Event, Ticket
from core.models import PlatformFlow, PlatformFlowEvent, CeleryTaskLog

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)
User = get_user_model()

@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def ticket_delivery_funnel(request):
    """
    Get ticket delivery funnel metrics.
    
    Returns counts and conversion rates for:
    - Paid orders
    - Emails enqueued
    - Emails sent
    - Emails failed
    """
    try:
        from core.models import PlatformFlow, PlatformFlowEvent, CeleryTaskLog
        from django.db.models import Count, Q
        from datetime import timedelta
        
        # Get date range from query params
        days = int(request.GET.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        # Get flow type filter
        flow_type = request.GET.get('flow_type', 'ticket_checkout')
        
        # Count paid orders
        paid_orders = Order.objects.filter(
            status='paid',
            created_at__gte=start_date
        ).count()
        
        # Count flows
        flows = PlatformFlow.objects.filter(
            flow_type=flow_type,
            created_at__gte=start_date
        )
        
        total_flows = flows.count()
        completed_flows = flows.filter(status='completed').count()
        failed_flows = flows.filter(status='failed').count()
        in_progress_flows = flows.filter(status='in_progress').count()
        
        # Count email events
        email_enqueued = PlatformFlowEvent.objects.filter(
            flow__created_at__gte=start_date,
            step='EMAIL_TASK_ENQUEUED'
        ).count()
        
        email_sent = PlatformFlowEvent.objects.filter(
            flow__created_at__gte=start_date,
            step='EMAIL_SENT',
            status='success'
        ).count()
        
        email_failed = PlatformFlowEvent.objects.filter(
            flow__created_at__gte=start_date,
            step='EMAIL_FAILED',
            status='failure'
        ).count()
        
        # Calculate conversion rates
        enqueue_rate = (email_enqueued / paid_orders * 100) if paid_orders > 0 else 0
        success_rate = (email_sent / email_enqueued * 100) if email_enqueued > 0 else 0
        failure_rate = (email_failed / email_enqueued * 100) if email_enqueued > 0 else 0
        completion_rate = (completed_flows / total_flows * 100) if total_flows > 0 else 0
        
        return Response({
            'success': True,
            'period': {
                'days': days,
                'start_date': start_date.isoformat(),
                'end_date': timezone.now().isoformat()
            },
            'funnel': {
                'paid_orders': paid_orders,
                'emails_enqueued': email_enqueued,
                'emails_sent': email_sent,
                'emails_failed': email_failed,
                'enqueue_rate': round(enqueue_rate, 2),
                'success_rate': round(success_rate, 2),
                'failure_rate': round(failure_rate, 2)
            },
            'flows': {
                'total': total_flows,
                'completed': completed_flows,
                'failed': failed_flows,
                'in_progress': in_progress_flows,
                'completion_rate': round(completion_rate, 2)
            }
        })
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting funnel: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting funnel: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def ticket_delivery_issues(request):
    """
    Get list of flows with delivery issues.
    
    Returns flows that:
    - Failed
    - Have email failures
    - Are stuck in progress for too long
    """
    try:
        from core.models import PlatformFlow, PlatformFlowEvent
        from datetime import timedelta
        
        # Get filters
        days = int(request.GET.get('days', 7))
        limit = int(request.GET.get('limit', 20))
        start_date = timezone.now() - timedelta(days=days)
        
        # Get failed flows
        failed_flows = PlatformFlow.objects.filter(
            status='failed',
            created_at__gte=start_date
        ).select_related('user', 'organizer', 'primary_order', 'event').order_by('-created_at')[:limit]
        
        # Get flows with email failures
        flows_with_email_failures = PlatformFlow.objects.filter(
            created_at__gte=start_date,
            events__step='EMAIL_FAILED'
        ).distinct().select_related('user', 'organizer', 'primary_order', 'event').order_by('-created_at')[:limit]
        
        # Get stuck flows (in progress for more than 1 hour)
        stuck_threshold = timezone.now() - timedelta(hours=1)
        stuck_flows = PlatformFlow.objects.filter(
            status='in_progress',
            created_at__lt=stuck_threshold
        ).select_related('user', 'organizer', 'primary_order', 'event').order_by('-created_at')[:limit]
        
        def serialize_flow(flow):
            # Get last event
            last_event = flow.events.order_by('-created_at').first()
            
            # Get email events (incluyendo reenvíos manuales)
            email_events = flow.events.filter(
                step__in=['EMAIL_TASK_ENQUEUED', 'EMAIL_SENT', 'EMAIL_FAILED',
                         'EMAIL_MANUAL_RESEND_SUCCESS', 'EMAIL_MANUAL_RESEND', 'EMAIL_MANUAL_RESEND_FAILED']
            ).order_by('-created_at')
            
            return {
                'id': str(flow.id),
                'flow_type': flow.flow_type,
                'status': flow.status,
                'created_at': flow.created_at.isoformat(),
                'completed_at': flow.completed_at.isoformat() if flow.completed_at else None,
                'failed_at': flow.failed_at.isoformat() if flow.failed_at else None,
                'user': {
                    'id': str(flow.user.id) if flow.user else None,
                    'email': flow.user.email if flow.user else None
                } if flow.user else None,
                'organizer': {
                    'id': str(flow.organizer.id) if flow.organizer else None,
                    'name': flow.organizer.name if flow.organizer else None
                } if flow.organizer else None,
                'order': {
                    'id': str(flow.primary_order.id) if flow.primary_order else None,
                    'order_number': flow.primary_order.order_number if flow.primary_order else None,
                    'total': float(flow.primary_order.total) if flow.primary_order else None
                } if flow.primary_order else None,
                'event': {
                    'id': str(flow.event.id) if flow.event else None,
                    'title': flow.event.title if flow.event else None
                } if flow.event else None,
                'last_event': {
                    'step': last_event.step,
                    'status': last_event.status,
                    'message': last_event.message,
                    'created_at': last_event.created_at.isoformat()
                } if last_event else None,
                'email_status': {
                    'enqueued': email_events.filter(step='EMAIL_TASK_ENQUEUED').exists(),
                    'sent': email_events.filter(step__in=['EMAIL_SENT', 'EMAIL_MANUAL_RESEND_SUCCESS']).exists(),
                    'failed': email_events.filter(step__in=['EMAIL_FAILED', 'EMAIL_MANUAL_RESEND_FAILED']).exists(),
                    'last_attempt': email_events.first().created_at.isoformat() if email_events.exists() else None
                }
            }
        
        return Response({
            'success': True,
            'issues': {
                'failed_flows': [serialize_flow(f) for f in failed_flows],
                'email_failures': [serialize_flow(f) for f in flows_with_email_failures],
                'stuck_flows': [serialize_flow(f) for f in stuck_flows]
            },
            'counts': {
                'failed': failed_flows.count(),
                'email_failures': flows_with_email_failures.count(),
                'stuck': stuck_flows.count()
            }
        })
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting issues: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting issues: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def events_list(request):
    """
    🚀 ENTERPRISE: Get list of events for filtering.
    
    Returns:
    - List of events with id and title
    """
    try:
        from apps.events.models import Event
        
        events = Event.objects.filter(
            deleted_at__isnull=True
        ).order_by('-created_at').values('id', 'title')[:100]  # Limit to 100 most recent
        
        return Response({
            'success': True,
            'events': list(events)
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting events list: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting events list: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def all_flows(request):
    """
    🚀 ENTERPRISE: Get ALL platform flows with filters and pagination.
    
    Query params:
    - days: Number of days to look back (default: 7)
    - status: Filter by status (completed, failed, in_progress, etc.)
    - flow_type: Filter by flow type (ticket_checkout, etc.)
    - search: Search by order_number, email, event title
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    """
    try:
        from core.models import PlatformFlow
        from django.db.models import Q
        
        logger.info("📊 [SuperAdmin] Getting all flows")
        
        # Get query parameters
        days = int(request.GET.get('days', 7))
        status_filter = request.GET.get('status', '')
        flow_type_filter = request.GET.get('flow_type', '')
        search = request.GET.get('search', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 20)), 100)
        
        # Calculate date range
        start_date = timezone.now() - timedelta(days=days)
        
        # Base queryset - Prefetch events with order for efficient lookup
        queryset = PlatformFlow.objects.filter(
            created_at__gte=start_date
        ).select_related('user', 'organizer', 'primary_order', 'event').prefetch_related('events__order')
        
        # Apply filters
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if flow_type_filter:
            queryset = queryset.filter(flow_type=flow_type_filter)
        
        # Apply event filter
        event_filter = request.GET.get('event_id', '')
        if event_filter:
            queryset = queryset.filter(event_id=event_filter)
        
        # 🚀 ENTERPRISE: Búsqueda inteligente en múltiples campos relacionados
        if search:
            from apps.events.models import Ticket, Order
            from django.db.models import Value, CharField
            from django.db.models.functions import Concat
            search_term = search.strip()
            search_words = search_term.split()
            
            # Construir Q objects para búsqueda en órdenes
            order_q = Q(order_number__icontains=search_term) | Q(email__icontains=search_term) | Q(phone__icontains=search_term)
            
            # Si hay múltiples palabras, buscar combinación de nombre y apellido
            if len(search_words) >= 2:
                # Buscar "nombre apellido" o "apellido nombre"
                first_word = search_words[0]
                second_word = search_words[1]
                
                # Combinación: first_name contiene primera palabra Y last_name contiene segunda palabra
                order_q |= (Q(first_name__icontains=first_word) & Q(last_name__icontains=second_word))
                # Combinación inversa: first_name contiene segunda palabra Y last_name contiene primera palabra
                order_q |= (Q(first_name__icontains=second_word) & Q(last_name__icontains=first_word))
                
                # También buscar cada palabra individualmente
                for word in search_words:
                    order_q |= Q(first_name__icontains=word) | Q(last_name__icontains=word)
            else:
                # Una sola palabra: buscar en first_name o last_name
                order_q |= Q(first_name__icontains=search_term) | Q(last_name__icontains=search_term)
            
            # Buscar órdenes que coincidan
            matching_order_ids = Order.objects.filter(order_q).values_list('id', flat=True)
            
            # Construir Q objects para búsqueda en tickets (asistentes)
            ticket_q = Q(email__icontains=search_term) | Q(ticket_number__icontains=search_term)
            
            # Si hay múltiples palabras, buscar combinación de nombre y apellido en tickets
            if len(search_words) >= 2:
                first_word = search_words[0]
                second_word = search_words[1]
                
                # Combinación: first_name contiene primera palabra Y last_name contiene segunda palabra
                ticket_q |= (Q(first_name__icontains=first_word) & Q(last_name__icontains=second_word))
                # Combinación inversa
                ticket_q |= (Q(first_name__icontains=second_word) & Q(last_name__icontains=first_word))
                
                # También buscar cada palabra individualmente
                for word in search_words:
                    ticket_q |= Q(first_name__icontains=word) | Q(last_name__icontains=word)
            else:
                # Una sola palabra
                ticket_q |= Q(first_name__icontains=search_term) | Q(last_name__icontains=search_term)
            
            # Buscar tickets que coincidan
            matching_ticket_order_ids = Ticket.objects.filter(ticket_q).values_list('order_item__order_id', flat=True).distinct()
            
            # Combinar todos los IDs de órdenes que coinciden
            all_matching_order_ids = set(list(matching_order_ids) + list(matching_ticket_order_ids))
            
            # Aplicar filtro en el queryset
            queryset = queryset.filter(
                Q(primary_order_id__in=all_matching_order_ids) |
                Q(user__email__icontains=search_term) |
                Q(event__title__icontains=search_term) |
                # También buscar en eventos del flow que tengan order_id
                Q(events__order_id__in=all_matching_order_ids)
            ).distinct()
        
        # Apply email status filter
        email_status_filter = request.GET.get('email_status', '')
        if email_status_filter:
            if email_status_filter == 'sent':
                # Incluir EMAIL_SENT y EMAIL_MANUAL_RESEND_SUCCESS
                queryset = queryset.filter(
                    events__step__in=['EMAIL_SENT', 'EMAIL_MANUAL_RESEND_SUCCESS'],
                    events__status='success'
                ).distinct()
            elif email_status_filter == 'failed':
                queryset = queryset.filter(
                    events__step__in=['EMAIL_FAILED', 'EMAIL_MANUAL_RESEND_FAILED']
                ).distinct()
            elif email_status_filter == 'enqueued':
                queryset = queryset.filter(events__step='EMAIL_TASK_ENQUEUED').distinct()
            elif email_status_filter == 'none':
                # Flows sin ningún evento de email
                queryset = queryset.exclude(
                    events__step__in=['EMAIL_TASK_ENQUEUED', 'EMAIL_SENT', 'EMAIL_FAILED',
                                    'EMAIL_MANUAL_RESEND', 'EMAIL_MANUAL_RESEND_SUCCESS', 'EMAIL_MANUAL_RESEND_FAILED']
                ).distinct()
        
        # Order by most recent
        queryset = queryset.order_by('-created_at')
        
        # Get total count
        total_count = queryset.count()
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        flows = queryset[start_idx:end_idx]
        
        # Serialize flows
        def serialize_flow(flow):
            # Get last event
            last_event = flow.events.order_by('-created_at').first()
            
            # Get email events (incluyendo reenvíos manuales)
            email_events = flow.events.filter(
                step__in=['EMAIL_TASK_ENQUEUED', 'EMAIL_SENT', 'EMAIL_FAILED', 
                         'EMAIL_MANUAL_RESEND_SUCCESS', 'EMAIL_MANUAL_RESEND']
            ).order_by('-created_at')
            
            # 🚀 ENTERPRISE: Buscar orden en primary_order o en eventos si no está en primary_order
            order = flow.primary_order
            if not order:
                # Buscar orden en los eventos del flow (prefetch ya cargado)
                order_event = flow.events.filter(order__isnull=False).select_related('order').first()
                if order_event and order_event.order:
                    order = order_event.order
                    # Actualizar primary_order para futuras consultas (sin bloquear)
                    try:
                        flow.primary_order = order
                        flow.save(update_fields=['primary_order'])
                        logger.info(f"📊 [SUPERADMIN] Found order {order.order_number} in flow {flow.id} events, updated primary_order")
                    except Exception as e:
                        logger.warning(f"⚠️ [SUPERADMIN] Could not update primary_order for flow {flow.id}: {e}")
                else:
                    # Debug: Log cuando no se encuentra orden
                    logger.debug(f"🔍 [SUPERADMIN] Flow {flow.id} has no order in primary_order or events")
            
            # 🚀 ENTERPRISE: Obtener primer asistente (ticket holder) de la orden
            attendee_name = None
            if order:
                try:
                    from apps.events.models import Ticket
                    # Optimizar: usar select_related para evitar N+1 queries
                    first_ticket = Ticket.objects.filter(
                        order_item__order=order
                    ).select_related('order_item').order_by('created_at').first()
                    if first_ticket:
                        attendee_name = f"{first_ticket.first_name} {first_ticket.last_name}".strip()
                except Exception as e:
                    logger.debug(f"🔍 [SUPERADMIN] Could not get attendee for order {order.order_number if order else 'N/A'}: {e}")
            
            # Calculate duration
            duration = None
            if flow.completed_at and flow.created_at:
                duration_delta = flow.completed_at - flow.created_at
                duration = str(duration_delta)
            elif flow.failed_at and flow.created_at:
                duration_delta = flow.failed_at - flow.created_at
                duration = str(duration_delta)
            
            return {
                'id': str(flow.id),
                'flow_type': flow.flow_type,
                'status': flow.status,
                'created_at': flow.created_at.isoformat(),
                'completed_at': flow.completed_at.isoformat() if flow.completed_at else None,
                'failed_at': flow.failed_at.isoformat() if flow.failed_at else None,
                'duration': duration,
                'user': {
                    'id': str(flow.user.id) if flow.user else None,
                    'email': flow.user.email if flow.user else None
                } if flow.user else None,
                'organizer': {
                    'id': str(flow.organizer.id) if flow.organizer else None,
                    'name': flow.organizer.name if flow.organizer else None
                } if flow.organizer else None,
                'order': {
                    'id': str(order.id) if order else None,
                    'order_number': order.order_number if order else None,
                    'total': float(order.total) if order else None,
                    'email': order.email if order else None
                } if order else None,
                'attendee_name': attendee_name,
                'event': {
                    'id': str(flow.event.id) if flow.event else None,
                    'title': flow.event.title if flow.event else None
                } if flow.event else None,
                'last_event': {
                    'step': last_event.step,
                    'status': last_event.status,
                    'message': last_event.message,
                    'created_at': last_event.created_at.isoformat()
                } if last_event else None,
                'email_status': {
                    'enqueued': email_events.filter(step='EMAIL_TASK_ENQUEUED').exists(),
                    'sent': email_events.filter(step__in=['EMAIL_SENT', 'EMAIL_MANUAL_RESEND_SUCCESS']).exists(),
                    'failed': email_events.filter(step__in=['EMAIL_FAILED', 'EMAIL_MANUAL_RESEND_FAILED']).exists(),
                    'last_attempt': email_events.first().created_at.isoformat() if email_events.exists() else None
                }
            }
        
        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size
        has_next = page < total_pages
        has_prev = page > 1
        
        logger.info(f"✅ [SuperAdmin] Found {total_count} flows (page {page}/{total_pages})")
        
        return Response({
            'success': True,
            'flows': [serialize_flow(f) for f in flows],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev
            },
            'filters': {
                'days': days,
                'status': status_filter,
                'flow_type': flow_type_filter,
                'search': search,
                'email_status': email_status_filter
            }
        })
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting all flows: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting flows: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def historical_conversion_rates(request):
    """
    🚀 ENTERPRISE: Get historical conversion rates for all steps.
    
    Query params:
        - from_date: ISO format start date (optional)
        - to_date: ISO format end date (optional)
        - organizer_id: Filter by organizer (optional)
        - event_id: Filter by event (optional)
    
    Returns step-by-step historical conversion rates.
    """
    try:
        from core.conversion_metrics import ConversionMetricsService, TICKET_CHECKOUT_STEPS
        from core.models import PlatformFlowEvent
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone
        
        # Parse date parameters
        from_date = None
        to_date = None
        if request.query_params.get('from_date'):
            from_date = parse_datetime(request.query_params.get('from_date'))
            if from_date and not timezone.is_aware(from_date):
                from_date = timezone.make_aware(from_date)
        
        if request.query_params.get('to_date'):
            to_date = parse_datetime(request.query_params.get('to_date'))
            if to_date and not timezone.is_aware(to_date):
                to_date = timezone.make_aware(to_date)
        
        organizer_id = request.query_params.get('organizer_id')
        event_id = request.query_params.get('event_id')
        
        # Get historical rates
        historical_rates = ConversionMetricsService.get_historical_conversion_rates(
            flow_type='ticket_checkout',
            from_date=from_date,
            to_date=to_date,
            organizer_id=organizer_id,
            event_id=event_id
        )
        
        # Format response with step display names
        step_display_map = dict(PlatformFlowEvent.STEP_CHOICES)
        
        steps_data = []
        for step in TICKET_CHECKOUT_STEPS:
            step_data = historical_rates.get(step, {})
            steps_data.append({
                'step': step,
                'step_display': step_display_map.get(step, step),
                'conversion_rate': step_data.get('conversion_rate', 0.0),
                'conversion_percentage': step_data.get('conversion_percentage', 0.0),
                'reached_count': step_data.get('reached_count', 0),
                'previous_count': step_data.get('previous_count'),
                'previous_step': step_data.get('previous_step')
            })
        
        # Calculate overall average
        overall_avg = sum(s.get('conversion_rate', 0.0) for s in historical_rates.values()) / len(historical_rates) if historical_rates else 0.0
        
        return Response({
            'success': True,
            'steps': steps_data,
            'overall_average': round(overall_avg, 4),
            'overall_average_percentage': round(overall_avg * 100, 2),
            'from_date': from_date.isoformat() if from_date else None,
            'to_date': to_date.isoformat() if to_date else None,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting historical conversion rates: {e}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting historical conversion rates: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def flow_detail(request, flow_id):
    """
    Get detailed information about a specific flow.
    
    Returns:
    - Flow information
    - All events in timeline
    - Related Celery tasks
    - Related email logs
    """
    try:
        from core.models import PlatformFlow, CeleryTaskLog
        from apps.events.models import EmailLog
        
        flow = PlatformFlow.objects.select_related(
            'user', 'organizer', 'primary_order', 'event', 'experience'
        ).prefetch_related('events__order').get(id=flow_id)
        
        # 🚀 ENTERPRISE: Buscar orden en primary_order o en eventos si no está en primary_order
        order = flow.primary_order
        if not order:
            # Buscar orden en los eventos del flow
            order_event = flow.events.filter(order__isnull=False).select_related('order').first()
            if order_event and order_event.order:
                order = order_event.order
                # Actualizar primary_order para futuras consultas
                try:
                    flow.primary_order = order
                    flow.save(update_fields=['primary_order'])
                    logger.info(f"📊 [SUPERADMIN] Found order {order.order_number} in flow {flow_id} events, updated primary_order")
                except Exception as e:
                    logger.warning(f"⚠️ [SUPERADMIN] Could not update primary_order for flow {flow_id}: {e}")
        
        # Get all events
        events = flow.events.select_related(
            'order', 'payment', 'email_log', 'celery_task_log'
        ).order_by('created_at')
        
        # Get Celery logs
        celery_logs = CeleryTaskLog.objects.filter(flow=flow).order_by('created_at')
        
        # Get email logs if order exists
        email_logs = []
        if order:
            email_logs = EmailLog.objects.filter(order=order).order_by('created_at')
        
        return Response({
            'success': True,
            'flow': {
                'id': str(flow.id),
                'flow_type': flow.flow_type,
                'status': flow.status,
                'created_at': flow.created_at.isoformat(),
                'completed_at': flow.completed_at.isoformat() if flow.completed_at else None,
                'failed_at': flow.failed_at.isoformat() if flow.failed_at else None,
                'metadata': flow.metadata,
                'user': {
                    'id': str(flow.user.id) if flow.user else None,
                    'email': flow.user.email if flow.user else None,
                    'name': f"{flow.user.first_name} {flow.user.last_name}" if flow.user else None
                } if flow.user else None,
                'organizer': {
                    'id': str(flow.organizer.id) if flow.organizer else None,
                    'name': flow.organizer.name if flow.organizer else None
                } if flow.organizer else None,
                'order': {
                    'id': str(order.id) if order else None,
                    'order_number': order.order_number if order else None,
                    'status': order.status if order else None,
                    'total': float(order.total) if order else None,
                    'email': order.email if order else None
                } if order else None,
                'event': {
                    'id': str(flow.event.id) if flow.event else None,
                    'title': flow.event.title if flow.event else None
                } if flow.event else None
            },
            'events': [{
                'id': str(e.id),
                'step': e.step,
                'status': e.status,
                'source': e.source,
                'message': e.message,
                'created_at': e.created_at.isoformat(),
                'metadata': e.metadata,
                'order_id': str(e.order.id) if e.order else None,
                'payment_id': str(e.payment.id) if e.payment else None,
                'email_log_id': str(e.email_log.id) if e.email_log else None,
                'celery_task_log_id': str(e.celery_task_log.id) if e.celery_task_log else None
            } for e in events],
            'celery_logs': [{
                'id': str(log.id),
                'task_id': log.task_id,
                'task_name': log.task_name,
                'status': log.status,
                'queue': log.queue,
                'created_at': log.created_at.isoformat(),
                'duration_ms': log.duration_ms,
                'error': log.error,
                'args': log.args,
                'kwargs': log.kwargs
            } for log in celery_logs],
            'email_logs': [{
                'id': str(log.id),
                'to_email': log.to_email,
                'subject': log.subject,
                'template': log.template,
                'status': log.status,
                'attempts': log.attempts,
                'error': log.error,
                'sent_at': log.sent_at.isoformat() if log.sent_at else None,
                'created_at': log.created_at.isoformat()
            } for log in email_logs]
        })
        
    except PlatformFlow.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Flow not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting flow detail: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting flow detail: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def resend_order_email(request, flow_id):
    """
    🚀 ENTERPRISE: Reenvía el email de confirmación de orden de forma SÍNCRONA (sin Celery).
    
    Similar a cómo se envían los OTP - instantáneo y directo.
    
    Body (opcional):
    - to_email: Email alternativo para enviar (si no se proporciona, usa el email de la orden)
    
    Returns:
    - success: bool
    - message: str
    - metrics: dict con tiempos de ejecución
    """
    try:
        from core.models import PlatformFlow
        from apps.events.email_sender import send_order_confirmation_email_optimized
        from core.flow_logger import FlowLogger
        
        # Get flow
        flow = PlatformFlow.objects.select_related('primary_order').prefetch_related('events__order').get(id=flow_id)
        
        # Si no hay orden en primary_order, intentar obtenerla de los eventos del flow
        order = flow.primary_order
        if not order:
            # Buscar orden en los eventos del flow
            order_event = flow.events.filter(order__isnull=False).select_related('order').first()
            if order_event and order_event.order:
                order = order_event.order
                logger.info(f"📧 [SUPERADMIN] Found order {order.order_number} in flow events, updating primary_order")
                # Actualizar el flow con la orden encontrada
                flow.primary_order = order
                flow.save(update_fields=['primary_order'])
        
        if not order:
            logger.warning(f"📧 [SUPERADMIN] Flow {flow_id} has no associated order")
            return Response({
                'success': False,
                'message': 'Este flow no tiene una orden asociada. No se puede reenviar el email de confirmación sin una orden.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get optional email override from request body
        to_email = None
        if request.data and isinstance(request.data, dict):
            to_email = request.data.get('to_email')
        
        # Use order email if no override provided
        if not to_email:
            to_email = order.email
        
        if not to_email:
            return Response({
                'success': False,
                'message': 'No email address available for order'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info(f"📧 [SUPERADMIN] Resending email for order {order.order_number} to {to_email} (synchronous)")
        
        # Log manual resend event BEFORE sending
        flow_logger = FlowLogger(flow)
        flow_logger.log_event(
            'EMAIL_MANUAL_RESEND',
            source='superadmin',
            status='info',
            message=f"Manual email resend initiated for order {order.order_number} to {to_email}",
            order=order,
            metadata={
                'resend_to': to_email,
                'resend_by': request.user.email if hasattr(request, 'user') and request.user.is_authenticated else 'superadmin',
            }
        )
        
        # Send email synchronously (like OTP)
        result = send_order_confirmation_email_optimized(
            order_id=str(order.id),
            to_email=to_email,
            flow_id=str(flow.id)
        )
        
        # Log result - send_order_confirmation_email_optimized returns 'completed' on success
        result_status = result.get('status')
        emails_sent = result.get('emails_sent', 0)
        failed_emails = result.get('failed_emails', [])
        
        if result_status == 'completed' and emails_sent > 0:
            logger.info(f"✅ [SUPERADMIN] Email resent successfully for order {order.order_number} - {emails_sent} email(s) sent")
            
            # Log successful manual resend
            flow_logger.log_event(
                'EMAIL_MANUAL_RESEND_SUCCESS',
                source='superadmin',
                status='success',
                message=f"Manual email resend completed successfully to {to_email}",
                order=order,
                metadata={
                    'resend_to': to_email,
                    'emails_sent': emails_sent,
                    'metrics': result.get('metrics', {}),
                }
            )
            
            return Response({
                'success': True,
                'message': f'Email enviado exitosamente a {to_email}',
                'metrics': result.get('metrics', {}),
                'status': result_status,
                'emails_sent': emails_sent
            }, status=status.HTTP_200_OK)
        elif result_status == 'completed' and emails_sent == 0:
            # Completed but no emails sent (shouldn't happen, but handle gracefully)
            error_msg = failed_emails[0].get('error', 'No emails sent') if failed_emails else 'No emails sent'
            logger.warning(f"⚠️ [SUPERADMIN] Email resend completed but no emails sent: {error_msg}")
            
            flow_logger.log_event(
                'EMAIL_MANUAL_RESEND_FAILED',
                source='superadmin',
                status='failure',
                message=f"Manual email resend failed: {error_msg}",
                order=order,
                metadata={
                    'resend_to': to_email,
                    'error': error_msg,
                    'failed_emails': failed_emails,
                    'metrics': result.get('metrics', {}),
                }
            )
            
            return Response({
                'success': False,
                'message': f'Error al enviar el email: {error_msg}',
                'metrics': result.get('metrics', {}),
                'status': result_status,
                'failed_emails': failed_emails
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # Error status
            error_msg = result.get('error', 'Unknown error')
            logger.warning(f"⚠️ [SUPERADMIN] Email resend returned status: {result_status} - {error_msg}")
            
            # Log failed manual resend
            flow_logger.log_event(
                'EMAIL_MANUAL_RESEND_FAILED',
                source='superadmin',
                status='failure',
                message=f"Manual email resend failed: {error_msg}",
                order=order,
                metadata={
                    'resend_to': to_email,
                    'error': error_msg,
                    'metrics': result.get('metrics', {}),
                }
            )
            
            return Response({
                'success': False,
                'message': f'Error al enviar el email: {error_msg}',
                'metrics': result.get('metrics', {}),
                'status': result_status
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except PlatformFlow.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Flow not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error resending email: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al reenviar email: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def bulk_resend_emails(request):
    """
    🚀 ENTERPRISE: Reenvía emails de múltiples flows de forma SÍNCRONA.
    
    Body:
    - flow_ids: Lista de flow IDs para reenviar
    
    Returns:
    - success: bool
    - results: Lista con resultado de cada reenvío
    - summary: Resumen de éxitos/fallos
    """
    try:
        from core.models import PlatformFlow
        from apps.events.email_sender import send_order_confirmation_email_optimized
        from core.flow_logger import FlowLogger
        import concurrent.futures
        from threading import Lock
        
        flow_ids = request.data.get('flow_ids', [])
        if not flow_ids or not isinstance(flow_ids, list):
            return Response({
                'success': False,
                'message': 'flow_ids debe ser una lista de IDs'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(flow_ids) > 50:
            return Response({
                'success': False,
                'message': 'Máximo 50 flows por lote'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info(f"📧 [SUPERADMIN] Bulk resend initiated for {len(flow_ids)} flows")
        
        results = []
        results_lock = Lock()
        
        def process_flow(flow_id: str):
            """Procesa un flow individual"""
            try:
                flow = PlatformFlow.objects.select_related('primary_order').prefetch_related('events__order').get(id=flow_id)
                
                # Buscar orden si no está en primary_order
                order = flow.primary_order
                if not order:
                    order_event = flow.events.filter(order__isnull=False).select_related('order').first()
                    if order_event and order_event.order:
                        order = order_event.order
                        flow.primary_order = order
                        flow.save(update_fields=['primary_order'])
                
                if not order:
                    return {
                        'flow_id': flow_id,
                        'success': False,
                        'message': 'Flow no tiene orden asociada',
                        'order_number': None
                    }
                
                to_email = order.email
                if not to_email:
                    return {
                        'flow_id': flow_id,
                        'success': False,
                        'message': 'Orden no tiene email',
                        'order_number': order.order_number
                    }
                
                # Log manual resend
                flow_logger = FlowLogger(flow)
                flow_logger.log_event(
                    'EMAIL_MANUAL_RESEND',
                    source='superadmin',
                    status='info',
                    message=f"Bulk manual email resend initiated for order {order.order_number}",
                    order=order,
                    metadata={'resend_to': to_email, 'bulk': True}
                )
                
                # Send email
                result = send_order_confirmation_email_optimized(
                    order_id=str(order.id),
                    to_email=to_email,
                    flow_id=str(flow.id)
                )
                
                result_status = result.get('status')
                emails_sent = result.get('emails_sent', 0)
                
                if result_status == 'completed' and emails_sent > 0:
                    flow_logger.log_event(
                        'EMAIL_MANUAL_RESEND_SUCCESS',
                        source='superadmin',
                        status='success',
                        message=f"Bulk manual email resend completed successfully",
                        order=order,
                        metadata={'resend_to': to_email, 'emails_sent': emails_sent, 'bulk': True}
                    )
                    
                    return {
                        'flow_id': flow_id,
                        'success': True,
                        'message': 'Email enviado exitosamente',
                        'order_number': order.order_number,
                        'email': to_email,
                        'metrics': result.get('metrics', {})
                    }
                else:
                    error_msg = result.get('error', 'No emails sent')
                    flow_logger.log_event(
                        'EMAIL_MANUAL_RESEND_FAILED',
                        source='superadmin',
                        status='failure',
                        message=f"Bulk manual email resend failed: {error_msg}",
                        order=order,
                        metadata={'resend_to': to_email, 'error': error_msg, 'bulk': True}
                    )
                    
                    return {
                        'flow_id': flow_id,
                        'success': False,
                        'message': error_msg,
                        'order_number': order.order_number,
                        'email': to_email
                    }
                    
            except PlatformFlow.DoesNotExist:
                return {
                    'flow_id': flow_id,
                    'success': False,
                    'message': 'Flow no encontrado',
                    'order_number': None
                }
            except Exception as e:
                logger.error(f"❌ [SUPERADMIN] Error processing flow {flow_id}: {str(e)}", exc_info=True)
                return {
                    'flow_id': flow_id,
                    'success': False,
                    'message': f'Error: {str(e)}',
                    'order_number': None
                }
        
        # Procesar en paralelo (máximo 5 simultáneos para no sobrecargar)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_flow = {executor.submit(process_flow, flow_id): flow_id for flow_id in flow_ids}
            for future in concurrent.futures.as_completed(future_to_flow):
                result = future.result()
                with results_lock:
                    results.append(result)
        
        # Calcular resumen
        successful = sum(1 for r in results if r.get('success'))
        failed = len(results) - successful
        
        logger.info(f"✅ [SUPERADMIN] Bulk resend completed: {successful} successful, {failed} failed")
        
        return Response({
            'success': True,
            'message': f'Procesados {len(results)} flows: {successful} exitosos, {failed} fallidos',
            'results': results,
            'summary': {
                'total': len(results),
                'successful': successful,
                'failed': failed
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error in bulk resend: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error en reenvío masivo: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


