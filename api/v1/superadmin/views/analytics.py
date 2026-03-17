"""
SuperAdmin Analytics Views
Endpoints para estadísticas y analytics de la plataforma.
"""

from datetime import timedelta
import logging

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Min, Sum, Q
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.events.models import Order, Event, OrderItem
from apps.organizers.models import Organizer
from core.revenue_system import order_revenue_eligible_q

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)
User = get_user_model()


def _parse_range(range_param):
    """Return (start_date, end_date) for range 7d, 30d, 1y. For 'all' use _first_activity_date()."""
    end = timezone.now().date()
    if range_param == "7d":
        start = end - timedelta(days=7)
    elif range_param == "30d":
        start = end - timedelta(days=30)
    elif range_param == "1y":
        start = end - timedelta(days=365)
    else:
        start = end - timedelta(days=365 * 5)  # fallback; "all" is overridden in dashboard_time_series
    return start, end


def _first_activity_date():
    """
    Fecha más antigua con actividad contable: primera orden con revenue, primer usuario,
    primer alojamiento, primera experiencia, primer organizador.
    Así "Todo" solo muestra desde que la plataforma tiene datos reales.
    """
    end = timezone.now().date()
    candidates = []
    # Primera orden con revenue
    first_order = (
        Order.objects.filter(order_revenue_eligible_q())
        .exclude(order_kind="erasmus_activity")
        .aggregate(m=Min("created_at"))
    )
    if first_order.get("m"):
        candidates.append(first_order["m"].date())
    # Primer usuario
    first_user = User.objects.aggregate(m=Min("date_joined"))
    if first_user.get("m"):
        candidates.append(first_user["m"].date())
    # Primer organizador
    first_org = Organizer.objects.aggregate(m=Min("created_at"))
    if first_org.get("m"):
        candidates.append(first_org["m"].date())
    try:
        from apps.accommodations.models import Accommodation
        first_acc = Accommodation.objects.aggregate(m=Min("created_at"))
        if first_acc.get("m"):
            candidates.append(first_acc["m"].date())
    except Exception:
        pass
    try:
        from apps.experiences.models import Experience
        first_exp = Experience.objects.aggregate(m=Min("created_at"))
        if first_exp.get("m"):
            candidates.append(first_exp["m"].date())
    except Exception:
        pass
    try:
        from apps.erasmus.models import ErasmusActivityInscriptionPayment
        first_erasmus = ErasmusActivityInscriptionPayment.objects.filter(
            exclude_from_revenue=False
        ).aggregate(m=Min("created_at"))
        if first_erasmus.get("m"):
            candidates.append(first_erasmus["m"].date())
    except Exception:
        pass
    try:
        from apps.car_rental.models import Car
        first_car = Car.objects.aggregate(m=Min("created_at"))
        if first_car.get("m"):
            candidates.append(first_car["m"].date())
    except Exception:
        pass
    if not candidates:
        return end - timedelta(days=365)
    return min(candidates)


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
        
        total_orders = Order.objects.filter(order_revenue_eligible_q()).count()
        total_revenue = Order.objects.filter(order_revenue_eligible_q()).aggregate(total=Sum('total'))['total'] or 0
        
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
        # Órdenes pagadas: excluir erasmus_activity, sandbox, eliminadas y excluidas (no cuentan en revenue)
        paid_orders = Order.objects.filter(order_revenue_eligible_q()).exclude(order_kind='erasmus_activity')
        
        # Ventas desde órdenes (eventos, experiencias, alojamientos, etc.)
        order_sales_raw = paid_orders.aggregate(total=Sum('subtotal'))['total'] or 0
        order_sales = float(order_sales_raw)
        
        # Cargos pagados (sumatoria de service_fee) solo de esas órdenes
        total_service_fees = paid_orders.aggregate(total=Sum('service_fee'))['total'] or 0
        total_service_fees = float(total_service_fees)
        
        # Ingresos por actividades Erasmus (manuales + plataforma), excluir cortesías/excluded
        erasmus_sales = 0.0
        try:
            from apps.erasmus.models import ErasmusActivityInscriptionPayment
            erasmus_payments = ErasmusActivityInscriptionPayment.objects.filter(
                exclude_from_revenue=False
            ).aggregate(total=Sum('amount'))
            erasmus_sales = float(erasmus_payments['total'] or 0)
        except Exception as erasmus_err:
            logger.warning("[SuperAdmin] Erasmus sales aggregation skipped: %s", erasmus_err)
        
        total_sales = order_sales + erasmus_sales
        
        # Número de órdenes pagadas (solo no-Erasmus; las Erasmus no son "órdenes" en este conteo para evitar confusión)
        paid_orders_count = paid_orders.count()
        
        # Ticket promedio (solo órdenes no-Erasmus)
        average_order_value = paid_orders.aggregate(avg=Sum('total'))['avg'] or 0
        if paid_orders_count > 0:
            average_order_value = float(average_order_value) / paid_orders_count
        else:
            average_order_value = 0.0
        
        # Ventas por tipo: eventos = solo órdenes con event (order_kind=event), revenue-eligible
        event_orders = Order.objects.filter(order_kind='event').filter(order_revenue_eligible_q())
        event_sales = float(event_orders.aggregate(total=Sum('subtotal'))['total'] or 0)
        event_fees = float(event_orders.aggregate(total=Sum('service_fee'))['total'] or 0)
        total_product_sales = order_sales + erasmus_sales
        event_pct = (event_sales / total_product_sales * 100) if total_product_sales > 0 else 0.0
        erasmus_pct = (erasmus_sales / total_product_sales * 100) if total_product_sales > 0 else 0.0
        
        # Top 5 eventos por ventas (solo órdenes de tipo event, con event no nulo, revenue-eligible)
        top_events = []
        events_sales_data = (
            Order.objects.filter(order_kind='event', event__isnull=False)
            .filter(order_revenue_eligible_q())
            .values('event')
            .annotate(
                total_sales=Sum('subtotal'),
                total_fees=Sum('service_fee'),
                orders_count=Count('id')
            )
            .order_by('-total_sales')[:5]
        )
        for event_data in events_sales_data:
            try:
                eid = event_data['event']
                if not eid:
                    continue
                event = Event.objects.get(id=eid)
                top_events.append({
                    'event_id': str(event.id),
                    'event_title': event.title,
                    'organizer_name': event.organizer.name if event.organizer else 'N/A',
                    'total_sales': float(event_data['total_sales'] or 0),
                    'total_fees': float(event_data['total_fees'] or 0),
                    'orders_count': event_data['orders_count']
                })
            except (Event.DoesNotExist, ValueError, TypeError):
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
            # Obtener órdenes pagadas de este evento (revenue-eligible)
            paid_orders = Order.objects.filter(event=event).filter(order_revenue_eligible_q())
            
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
                order__status='paid',
                order__is_sandbox=False,
                order__deleted_at__isnull=True,
                order__exclude_from_revenue=False,
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
            # Obtener todas las órdenes pagadas de eventos de este organizador (revenue-eligible)
            paid_orders = Order.objects.filter(
                event__organizer=organizer,
            ).filter(order_revenue_eligible_q())
            
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


def _parse_date(s):
    """Parse YYYY-MM-DD string to date; return None if invalid."""
    if not s or not isinstance(s, str):
        return None
    try:
        from datetime import date
        return date.fromisoformat(s.strip()[:10])
    except (ValueError, TypeError):
        return None


@api_view(['GET'])
@permission_classes([IsSuperUser])
def dashboard_time_series(request):
    """
    📈 Series temporales para el dashboard SuperAdmin.

    GET /api/v1/superadmin/dashboard-time-series/?range=7d|30d|1y|all
    GET /api/v1/superadmin/dashboard-time-series/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

    - revenue: nuestro revenue (comisiones Tuki = service_fee) por día + acumulado.
    - users, accommodations, experiences, organizers, transports: nuevos por día + acumulado.
    - summary: revenue_last_7d, revenue_last_30d, users_new_7d, users_new_30d, organizers_new_7d, organizers_new_30d.
    """
    try:
        today = timezone.now().date()
        custom_start = _parse_date(request.query_params.get("start_date"))
        custom_end = _parse_date(request.query_params.get("end_date"))

        if custom_start is not None and custom_end is not None:
            if custom_start > custom_end:
                custom_start, custom_end = custom_end, custom_start
            max_days = 365 * 10
            if (custom_end - custom_start).days > max_days:
                custom_end = custom_start + timedelta(days=max_days)
            start_date = custom_start
            end_date = min(custom_end, today)
            range_param = "custom"
        else:
            range_param = (request.query_params.get("range") or "30d").strip().lower()
            if range_param not in ("7d", "30d", "1y", "all"):
                range_param = "30d"
            start_date, end_date = _parse_range(range_param)
            if range_param == "all":
                start_date = _first_activity_date()
            end_date = min(end_date, today)

        # --- Revenue por día: efectivo (service_fee_effective, con descuentos/impuestos) o fallback a service_fee
        paid_orders = (
            Order.objects.filter(order_revenue_eligible_q())
            .exclude(order_kind="erasmus_activity")
            .filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
        )
        revenue_by_date = (
            paid_orders.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(revenue=Sum(Coalesce(F("service_fee_effective"), F("service_fee"))))
            .order_by("day")
        )
        revenue_map = {item["day"].isoformat() if item["day"] else None: float(item["revenue"] or 0) for item in revenue_by_date if item["day"]}

        # Erasmus: ingresos plataforma (si hay fee o monto que cuente como revenue)
        try:
            from apps.erasmus.models import ErasmusActivityInscriptionPayment
            erasmus_by_date = (
                ErasmusActivityInscriptionPayment.objects.filter(exclude_from_revenue=False)
                .filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
                .annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(amount=Sum("amount"))
                .order_by("day")
            )
            for item in erasmus_by_date:
                if item["day"]:
                    k = item["day"].isoformat()
                    revenue_map[k] = revenue_map.get(k, 0) + float(item["amount"] or 0)
        except Exception:
            pass

        # Build sorted list of all days in range
        days = []
        d = start_date
        while d <= end_date:
            days.append(d)
            d += timedelta(days=1)
        day_strs = [d.isoformat() for d in days]

        revenue_series = []
        cumulative = 0
        for day_str in day_strs:
            rev = revenue_map.get(day_str, 0)
            cumulative += rev
            revenue_series.append({
                "date": day_str,
                "value": round(rev, 0),
                "cumulative": round(cumulative, 0),
            })

        # --- Usuarios por día (date_joined)
        users_agg = (
            User.objects.filter(date_joined__date__gte=start_date, date_joined__date__lte=end_date)
            .annotate(day=TruncDate("date_joined"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        users_map = {item["day"].isoformat() if item["day"] else None: item["count"] for item in users_agg if item["day"]}
        # Cumulative: total users up to each day (users with date_joined <= day)
        users_series = []
        cum_users = 0
        for day_str in day_strs:
            new_count = users_map.get(day_str, 0)
            cum_users += new_count
            users_series.append({"date": day_str, "value": new_count, "cumulative": cum_users})

        # --- Alojamientos por día (created_at)
        try:
            from apps.accommodations.models import Accommodation
            acc_agg = (
                Accommodation.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
                .annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(count=Count("id"))
                .order_by("day")
            )
            acc_map = {item["day"].isoformat() if item["day"] else None: item["count"] for item in acc_agg if item["day"]}
        except Exception:
            acc_map = {}
        acc_cum = 0
        accommodations_series = []
        for day_str in day_strs:
            new_count = acc_map.get(day_str, 0)
            acc_cum += new_count
            accommodations_series.append({"date": day_str, "value": new_count, "cumulative": acc_cum})

        # --- Experiencias por día (created_at)
        try:
            from apps.experiences.models import Experience
            exp_agg = (
                Experience.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
                .annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(count=Count("id"))
                .order_by("day")
            )
            exp_map = {item["day"].isoformat() if item["day"] else None: item["count"] for item in exp_agg if item["day"]}
        except Exception:
            exp_map = {}
        exp_cum = 0
        experiences_series = []
        for day_str in day_strs:
            new_count = exp_map.get(day_str, 0)
            exp_cum += new_count
            experiences_series.append({"date": day_str, "value": new_count, "cumulative": exp_cum})

        # --- Organizadores por día (created_at)
        org_agg = (
            Organizer.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        org_map = {item["day"].isoformat() if item["day"] else None: item["count"] for item in org_agg if item["day"]}
        org_cum = 0
        organizers_series = []
        for day_str in day_strs:
            new_count = org_map.get(day_str, 0)
            org_cum += new_count
            organizers_series.append({"date": day_str, "value": new_count, "cumulative": org_cum})

        # --- Transportes (autos/vehículos rent-a-car) por día (created_at)
        try:
            from apps.car_rental.models import Car
            car_agg = (
                Car.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
                .annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(count=Count("id"))
                .order_by("day")
            )
            car_map = {item["day"].isoformat() if item["day"] else None: item["count"] for item in car_agg if item["day"]}
        except Exception:
            car_map = {}
        car_cum = 0
        transports_series = []
        for day_str in day_strs:
            new_count = car_map.get(day_str, 0)
            car_cum += new_count
            transports_series.append({"date": day_str, "value": new_count, "cumulative": car_cum})

        # Summary: últimos 7 y 30 días (para tarjetas: "Última semana", "Último mes")
        n = len(revenue_series)
        rev_7 = sum(p["value"] for p in revenue_series[-7:]) if n >= 1 else 0
        rev_30 = sum(p["value"] for p in revenue_series[-30:]) if n >= 1 else 0
        users_7 = sum(p["value"] for p in users_series[-7:]) if len(users_series) >= 1 else 0
        users_30 = sum(p["value"] for p in users_series[-30:]) if len(users_series) >= 1 else 0
        org_7 = sum(p["value"] for p in organizers_series[-7:]) if len(organizers_series) >= 1 else 0
        org_30 = sum(p["value"] for p in organizers_series[-30:]) if len(organizers_series) >= 1 else 0
        summary = {
            "revenue_last_7d": round(rev_7, 0),
            "revenue_last_30d": round(rev_30, 0),
            "users_new_7d": users_7,
            "users_new_30d": users_30,
            "organizers_new_7d": org_7,
            "organizers_new_30d": org_30,
        }

        return Response({
            "success": True,
            "range": range_param,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "revenue": revenue_series,
            "users": users_series,
            "accommodations": accommodations_series,
            "experiences": experiences_series,
            "organizers": organizers_series,
            "transports": transports_series,
            "summary": summary,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error("❌ [SuperAdmin] Error dashboard_time_series: %s", str(e), exc_info=True)
        return Response({
            "success": False,
            "message": str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
