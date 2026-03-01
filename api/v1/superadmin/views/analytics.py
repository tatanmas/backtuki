"""
SuperAdmin Analytics Views
Endpoints para estadísticas y analytics de la plataforma.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Q
import logging

from apps.events.models import Order, Event, OrderItem
from apps.organizers.models import Organizer

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)
User = get_user_model()


@api_view(['GET'])
@permission_classes([IsSuperUser])
def superadmin_stats(request):
    """
    📊 Estadísticas generales del Super Admin
    
    GET /api/v1/superadmin/stats/
    """
    try:
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        organizers = User.objects.filter(is_organizer=True).count()
        guests = User.objects.filter(is_guest=True).count()
        
        total_orders = Order.objects.filter(status='paid').count()
        total_revenue = Order.objects.filter(status='paid').aggregate(
            total=Sum('total')
        )['total'] or 0
        
        recent_users = User.objects.order_by('-date_joined')[:5]
        recent_users_data = [{
            'id': user.id,
            'email': user.email,
            'full_name': user.get_full_name(),
            'date_joined': user.date_joined.isoformat()
        } for user in recent_users]
        
        return Response({
            'success': True,
            'stats': {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': total_users - active_users,
                'organizers': organizers,
                'guests': guests,
                'total_orders': total_orders,
                'total_revenue': float(total_revenue),
                'recent_users': recent_users_data
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting stats: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error al obtener estadísticas: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def sales_analytics(request):
    """
    💰 Analytics de ventas de la plataforma
    
    GET /api/v1/superadmin/sales-analytics/
    
    Returns:
        - Ventas efectivas totales (sumatoria de subtotales pagados)
        - Cargos pagados totales (sumatoria de service_fee pagados)
        - Ventas por tipo de producto (eventos, experiencias, alojamientos)
        - Número de órdenes pagadas
        - Ticket promedio
    """
    try:
        # Obtener todas las órdenes pagadas
        paid_orders = Order.objects.filter(status='paid')
        
        # Calcular ventas efectivas (sumatoria de subtotales)
        total_sales = paid_orders.aggregate(total=Sum('subtotal'))['total'] or 0
        
        # Calcular cargos pagados (sumatoria de service_fee)
        total_service_fees = paid_orders.aggregate(total=Sum('service_fee'))['total'] or 0
        
        # Ingresos por actividades Erasmus (pagos manuales desde lista invitados)
        from apps.erasmus.models import ErasmusActivityInscriptionPayment
        erasmus_payments = ErasmusActivityInscriptionPayment.objects.aggregate(total=Sum('amount'))
        erasmus_sales = float(erasmus_payments['total'] or 0)
        order_sales = float(total_sales)
        total_sales = order_sales + erasmus_sales
        
        # Número de órdenes pagadas
        paid_orders_count = paid_orders.count()
        
        # Ticket promedio (incluyendo service fee)
        average_order_value = paid_orders.aggregate(avg=Sum('total'))['avg'] or 0
        if paid_orders_count > 0:
            average_order_value = average_order_value / paid_orders_count
        
        # Ventas por tipo de producto
        event_sales = order_sales
        event_fees = total_service_fees
        total_product_sales = order_sales + erasmus_sales
        event_pct = (event_sales / total_product_sales * 100) if total_product_sales > 0 else 0.0
        erasmus_pct = (erasmus_sales / total_product_sales * 100) if total_product_sales > 0 else 0.0
        
        # Top 5 eventos por ventas
        top_events = []
        events_sales_data = paid_orders.values('event').annotate(
            total_sales=Sum('subtotal'),
            total_fees=Sum('service_fee'),
            orders_count=Count('id')
        ).order_by('-total_sales')[:5]
        
        for event_data in events_sales_data:
            try:
                event = Event.objects.get(id=event_data['event'])
                top_events.append({
                    'event_id': str(event.id),
                    'event_title': event.title,
                    'organizer_name': event.organizer.name if event.organizer else 'N/A',
                    'total_sales': float(event_data['total_sales'] or 0),
                    'total_fees': float(event_data['total_fees'] or 0),
                    'orders_count': event_data['orders_count']
                })
            except Event.DoesNotExist:
                continue
        
        logger.info(f"✅ [SuperAdmin] Sales analytics calculated: ${total_sales} in sales, ${total_service_fees} in fees")
        
        return Response({
            'success': True,
            'analytics': {
                # Ventas efectivas (lo que va a organizadores)
                'total_sales': float(total_sales),
                # Cargos pagados (lo que va a la plataforma)
                'total_service_fees': float(total_service_fees),
                # Total bruto (ventas + cargos)
                'gross_total': float(total_sales + total_service_fees),
                # Estadísticas
                'paid_orders_count': paid_orders_count,
                'average_order_value': float(average_order_value),
                # Ventas por tipo (por ahora solo eventos)
                'by_type': {
                    'events': {
                        'sales': float(event_sales),
                        'fees': float(event_fees),
                        'percentage': round(event_pct, 2)
                    },
                    'experiences': {
                        'sales': 0.0,
                        'fees': 0.0,
                        'percentage': 0.0
                    },
                    'accommodations': {
                        'sales': 0.0,
                        'fees': 0.0,
                        'percentage': 0.0
                    },
                    'erasmus_activities': {
                        'sales': float(erasmus_sales),
                        'fees': 0.0,
                        'percentage': round(erasmus_pct, 2)
                    }
                },
                # Top eventos
                'top_events': top_events
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting sales analytics: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al obtener analytics de ventas: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def events_analytics(request):
    """
    📅 Analytics de eventos de la plataforma
    
    GET /api/v1/superadmin/events-analytics/
    
    Query Params:
        - organizer_id (optional): Filtrar por organizador específico
        - status (optional): Filtrar por estado (published, draft, cancelled, etc.)
    
    Returns:
        Lista de eventos con sus estadísticas de ventas
    """
    try:
        organizer_id = request.query_params.get('organizer_id')
        status_filter = request.query_params.get('status')
        
        # Base queryset de eventos
        events_qs = Event.objects.select_related('organizer', 'location').all()
        
        if organizer_id:
            events_qs = events_qs.filter(organizer_id=organizer_id)
        
        if status_filter:
            events_qs = events_qs.filter(status=status_filter)
        
        # Calcular estadísticas por evento
        events_data = []
        
        for event in events_qs:
            # Obtener órdenes pagadas de este evento
            paid_orders = Order.objects.filter(
                event=event,
                status='paid'
            )
            
            # Calcular totales
            sales_data = paid_orders.aggregate(
                total_sales=Sum('subtotal'),
                total_fees=Sum('service_fee'),
                total_amount=Sum('total'),
                orders_count=Count('id')
            )
            
            # Calcular tickets vendidos
            tickets_sold = OrderItem.objects.filter(
                order__event=event,
                order__status='paid'
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            # 🚀 Calcular service fee efectivo siguiendo jerarquía: Event > Organizer > Platform
            if event.service_fee_rate is not None:
                effective_fee_rate = float(event.service_fee_rate)
                service_fee_source = 'event'
            elif event.organizer.default_service_fee_rate is not None:
                effective_fee_rate = float(event.organizer.default_service_fee_rate)
                service_fee_source = 'organizer'
            else:
                effective_fee_rate = 0.15  # Platform default
                service_fee_source = 'platform'
            
            # Calcular tasa de comisión efectiva (para mostrar en porcentaje)
            total_sales = float(sales_data['total_sales'] or 0)
            total_fees = float(sales_data['total_fees'] or 0)
            effective_fee_percentage = 0
            if total_sales > 0:
                effective_fee_percentage = (total_fees / total_sales) * 100
            
            events_data.append({
                'id': str(event.id),
                'title': event.title,
                'slug': event.slug,
                'status': event.status,
                'organizer_id': str(event.organizer.id),
                'organizer_name': event.organizer.name,
                'start_date': event.start_date.isoformat() if event.start_date else None,
                'end_date': event.end_date.isoformat() if event.end_date else None,
                'location': event.location.name if event.location else 'Sin ubicación',
                'location_address': event.location.address if event.location else '',
                'pricing_mode': event.pricing_mode,
                'is_free': event.is_free,
                # Estadísticas de ventas
                'total_sales': total_sales,
                'total_service_fees': total_fees,
                'gross_total': float(sales_data['total_amount'] or 0),
                'tickets_sold': tickets_sold,
                'orders_count': sales_data['orders_count'] or 0,
                'effective_fee_rate': round(effective_fee_percentage, 2),  # En porcentaje para compatibilidad
                'effective_service_fee_rate': effective_fee_rate,  # En decimal (0.0 a 1.0)
                'service_fee_rate': float(event.service_fee_rate) if event.service_fee_rate is not None else None,  # Fee configurado del evento (puede ser null)
                'service_fee_source': service_fee_source,  # 'event' | 'organizer' | 'platform'
                'configured_fee_rate': float(event.service_fee_rate * 100) if event.service_fee_rate else (float(event.organizer.default_service_fee_rate * 100) if event.organizer.default_service_fee_rate else 0),
                # Metadatos
                'created_at': event.created_at.isoformat(),
                'updated_at': event.updated_at.isoformat(),
            })
        
        # Ordenar por ventas totales descendente
        events_data.sort(key=lambda x: x['total_sales'], reverse=True)
        
        logger.info(f"✅ [SuperAdmin] Events analytics calculated for {len(events_data)} events")
        
        return Response({
            'success': True,
            'count': len(events_data),
            'events': events_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting events analytics: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al obtener analytics de eventos: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def organizer_sales(request):
    """
    📊 Ventas por organizador
    
    GET /api/v1/superadmin/organizer-sales/
    
    Query Params:
        - organizer_id (optional): Filtrar por organizador específico
    
    Returns:
        Lista de organizadores con sus ventas y comisiones generadas
    """
    try:
        organizer_id = request.query_params.get('organizer_id')
        
        # Base queryset de organizadores
        organizers_qs = Organizer.objects.all()
        
        if organizer_id:
            organizers_qs = organizers_qs.filter(id=organizer_id)
        
        # Calcular ventas por organizador
        organizers_data = []
        
        for organizer in organizers_qs:
            # Obtener todas las órdenes pagadas de eventos de este organizador
            paid_orders = Order.objects.filter(
                event__organizer=organizer,
                status='paid'
            )
            
            # Calcular totales
            sales_data = paid_orders.aggregate(
                total_sales=Sum('subtotal'),
                total_fees=Sum('service_fee'),
                orders_count=Count('id')
            )
            
            total_sales = float(sales_data['total_sales'] or 0)
            total_fees = float(sales_data['total_fees'] or 0)
            orders_count = sales_data['orders_count'] or 0
            
            # Calcular tasa de comisión promedio
            avg_fee_percentage = 0
            if total_sales > 0:
                avg_fee_percentage = (total_fees / total_sales) * 100
            
            # 🚀 Contar productos por tipo
            events_count = Event.objects.filter(organizer=organizer, deleted_at__isnull=True).count()
            
            experiences_count = 0
            if organizer.has_experience_module:
                try:
                    from apps.experiences.models import Experience
                    experiences_count = Experience.objects.filter(organizer=organizer, deleted_at__isnull=True).count()
                except Exception:
                    pass
            
            accommodations_count = 0
            if organizer.has_accommodation_module:
                try:
                    from apps.accommodations.models import Accommodation
                    accommodations_count = Accommodation.objects.filter(organizer=organizer, deleted_at__isnull=True).count()
                except Exception:
                    pass
            
            # 🚀 Service fee efectivo (siguiendo jerarquía)
            effective_service_fee_rate = float(organizer.default_service_fee_rate) if organizer.default_service_fee_rate is not None else 0.15
            service_fee_source = 'organizer' if organizer.default_service_fee_rate is not None else 'platform'
            
            # Normalize legacy template values
            template = organizer.experience_dashboard_template
            if template == 'standard':
                template = 'v0'
            elif template == 'free_tours':
                template = 'principal'
            
            organizers_data.append({
                'organizer_id': str(organizer.id),
                'organizer_name': organizer.name,
                'organizer_email': organizer.contact_email,
                'total_sales': total_sales,
                'total_service_fees': total_fees,
                'gross_total': total_sales + total_fees,
                'orders_count': orders_count,
                'average_fee_percentage': round(avg_fee_percentage, 2),
                # 🚀 Service fee configurado (puede ser null)
                'default_service_fee_rate': float(organizer.default_service_fee_rate) if organizer.default_service_fee_rate is not None else None,
                # 🚀 Service fee efectivo
                'effective_service_fee_rate': effective_service_fee_rate,
                'service_fee_source': service_fee_source,
                'status': organizer.status,
                # 🚀 Módulos activos
                'has_events_module': organizer.has_events_module,
                'has_experience_module': organizer.has_experience_module,
                'has_accommodation_module': organizer.has_accommodation_module,
                # 🚀 Centro de Alumnos
                'is_student_center': organizer.is_student_center,
                # 🚀 Template de dashboard de experiencias (normalizado)
                'experience_dashboard_template': template,
                # 🚀 Conteos de productos
                'events_count': events_count,
                'experiences_count': experiences_count,
                'accommodations_count': accommodations_count,
            })
        
        # Ordenar por ventas totales descendente
        organizers_data.sort(key=lambda x: x['total_sales'], reverse=True)
        
        logger.info(f"✅ [SuperAdmin] Organizer sales calculated for {len(organizers_data)} organizers")
        
        return Response({
            'success': True,
            'count': len(organizers_data),
            'organizers': organizers_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting organizer sales: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al obtener ventas por organizador: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
