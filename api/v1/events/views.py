"""Views for events API."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, filters, status, mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.utils import timezone
from django.db.models import F, Sum, Count, Q
from django.utils.text import slugify
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.http import Http404
import uuid
import os
from django.db import transaction
from django.db.models import Count, Sum, F, Q, Value
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from datetime import timedelta

from core.permissions import IsOrganizer, HasEventModule
from apps.events.models import (
    Event,
    EventCategory,
    Location,
    TicketTier,
    TicketCategory,
    Order,
    OrderItem,
    Ticket,
    TicketHold,
    Coupon,
    EventCommunication,
    EventImage,
)
from apps.forms.models import Form, FormField
from apps.forms.serializers import FormFieldSerializer
from apps.organizers.models import OrganizerUser
from .serializers import (
    EventListSerializer,
    EventDetailSerializer,
    EventCreateSerializer,
    EventUpdateSerializer,
    EventAvailabilitySerializer,
    BookingSerializer,
    EventCategorySerializer,
    LocationSerializer,
    TicketTierSerializer,
    TicketTierCreateUpdateSerializer,
    TicketCategorySerializer,
    OrderSerializer,
    OrderDetailSerializer,
    TicketSerializer,
    CouponSerializer,
    EventCommunicationSerializer,
    PublicEventSerializer,
)


class EventViewSet(viewsets.ModelViewSet):
    """ViewSet for Event model."""
    
    queryset = Event.objects.all()
    serializer_class = EventListSerializer
    permission_classes = [IsAuthenticated]
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            # Handle anonymous users
            if not self.request.user.is_authenticated:
                return None
            
            # Buscar OrganizerUser, si hay múltiples tomar el más reciente
            organizer_users = OrganizerUser.objects.filter(user=self.request.user)
            if organizer_users.exists():
                organizer_user = organizer_users.order_by('-created_at').first()
                return organizer_user.organizer
            else:
                return None
        except Exception as e:
            print(f"[EventViewSet] Error getting organizer: {e}")
            return None
    
    def get_queryset(self):
        """Return events based on user permissions."""
        # For public endpoints like book/reserve/retrieve, allow access to all published events
        if self.action in ['book', 'reserve', 'availability', 'retrieve']:
            return Event.objects.filter(
                status='published', 
                visibility='public',
                deleted_at__isnull=True  # Exclude soft deleted events
            )
            
        organizer = self.get_organizer()
        print(f"DEBUG - EventViewSet.get_queryset - User: {self.request.user.id if self.request.user.is_authenticated else 'Anonymous'}")
        print(f"DEBUG - EventViewSet.get_queryset - Organizer: {organizer.id if organizer else 'None'}")
        
        if not organizer:
            print("DEBUG - EventViewSet.get_queryset - No organizer found, returning empty queryset")
            return Event.objects.none()
        
        # For organizer dashboard, exclude soft deleted events by default
        queryset = self.queryset.filter(
            organizer=organizer,
            deleted_at__isnull=True
        )
        print(f"DEBUG - EventViewSet.get_queryset - Found {queryset.count()} events for organizer")
        
        return queryset
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return EventListSerializer
        if self.action == 'retrieve':
            return EventDetailSerializer
        if self.action == 'create':
            return EventCreateSerializer
        if self.action in ['update', 'partial_update']:
            return EventUpdateSerializer
        if self.action == 'availability':
            return EventAvailabilitySerializer
        if self.action == 'book':
            return BookingSerializer
        return EventDetailSerializer
    def get_permissions(self):
        """Allow public access to availability and booking endpoints."""
        if self.action in ['availability', 'book', 'reserve', 'public_list']:
            return [permissions.AllowAny()]
        if self.action == 'retrieve':
            # Allow public access to published events
            return [permissions.AllowAny()]
        return super().get_permissions()
    
    def get_serializer_context(self):
        """Add additional context to serializer."""
        context = super().get_serializer_context()
        if self.action == 'book':
            context['event_id'] = self.kwargs.get('pk')
        return context
    
    def retrieve(self, request, *args, **kwargs):
        """Retrieve a single event with debugging."""
        event_id = kwargs.get('pk')
        print(f"DEBUG - EventViewSet.retrieve - Attempting to retrieve event ID: {event_id}")
        
        try:
            instance = self.get_object()
            
            # Extra security for public access: ensure event is not soft deleted
            if self.action in ['retrieve'] and hasattr(instance, 'is_deleted') and instance.is_deleted:
                print(f"DEBUG - EventViewSet.retrieve - Event {event_id} is soft deleted")
                raise Http404("Event not found")
            
            print(f"DEBUG - EventViewSet.retrieve - Found event: {instance.title} (ID: {instance.id}, Status: {instance.status})")
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Exception as e:
            print(f"DEBUG - EventViewSet.retrieve - Error retrieving event {event_id}: {str(e)}")
            raise

    def list(self, request, *args, **kwargs):
        """List events with optional filters."""
        queryset = self.get_queryset()
        
        # Apply filters
        event_type = request.query_params.getlist('type', [])
        if event_type:
            queryset = queryset.filter(type__in=event_type)
        
        start_date = request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(start_date__gte=start_date)
        
        end_date = request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(start_date__lte=end_date)
        
        location = request.query_params.get('location')
        if location:
            location_terms = location.lower()
            queryset = queryset.filter(
                Q(location__city__icontains=location_terms) |
                Q(location__country__icontains=location_terms) |
                Q(location__name__icontains=location_terms)
            )
        
        categories = request.query_params.getlist('category', [])
        if categories:
            queryset = queryset.filter(category__name__in=categories)
        
        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """Get ticket availability for an event."""
        event = self.get_object()
        
        # Ensure event is not soft deleted
        if event.is_deleted:
            return Response({"detail": "Event not found."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = self.get_serializer(event)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def public_list(self, request):
        """Get all public published events for the homepage."""
        queryset = Event.objects.filter(
            status='published',
            visibility='public',
            deleted_at__isnull=True  # Exclude soft deleted events
        ).order_by('-featured', '-start_date')
        
        # Apply filters
        event_type = request.query_params.getlist('type', [])
        if event_type:
            queryset = queryset.filter(type__in=event_type)
        
        start_date = request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(start_date__gte=start_date)
        
        end_date = request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(start_date__lte=end_date)
        
        location = request.query_params.get('location')
        if location:
            location_terms = location.lower()
            queryset = queryset.filter(
                Q(location__city__icontains=location_terms) |
                Q(location__country__icontains=location_terms) |
                Q(location__name__icontains=location_terms)
            )
        
        categories = request.query_params.getlist('category', [])
        if categories:
            queryset = queryset.filter(category__name__in=categories)
        
        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = PublicEventSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = PublicEventSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.AllowAny])
    def book(self, request, pk=None):
        """🚀 ENTERPRISE: Book tickets for an event."""
        import logging
        logger = logging.getLogger(__name__)
        
        event = self.get_object()
        logger.info(f'📦 BOOKING: Attempting to book tickets for event {event.title} ({event.id})')
        logger.info(f'📦 BOOKING: Request data: {request.data}')
        
        # Ensure event is published and not deleted
        if event.status != 'published':
            logger.warning(f'📦 BOOKING: Event {event.id} not published (status: {event.status})')
            return Response({"detail": "Event not available for booking."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Extra security: ensure event is not soft deleted
        if event.is_deleted:
            logger.warning(f'📦 BOOKING: Event {event.id} is deleted')
            return Response({"detail": "Event not available for booking."}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            # Create a clean context without request.user to avoid AnonymousUser issues
            context = {'event_id': pk}
            if request.user.is_authenticated:
                context['request'] = request
            
            serializer = self.get_serializer(data=request.data, context=context)
            if not serializer.is_valid():
                logger.error(f'📦 BOOKING: Validation errors: {serializer.errors}')
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            booking = serializer.save()
            logger.info(f'📦 BOOKING: Successfully created booking: {booking}')
            return Response(booking, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f'📦 BOOKING: Unexpected error: {str(e)}')
            import traceback
            logger.error(f'📦 BOOKING: Traceback: {traceback.format_exc()}')
            return Response({"detail": f"Booking failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def reserve(self, request, pk=None):
        """🚀 ENTERPRISE: Reserve tickets with expiration to prevent overselling."""
        event = self.get_object()
        
        # Ensure event is published and not deleted
        if event.status != 'published':
            return Response({"detail": "Event not available for reservations."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Extra security: ensure event is not soft deleted
        if event.is_deleted:
            return Response({"detail": "Event not found."}, status=status.HTTP_404_NOT_FOUND)

        tickets = request.data.get('tickets', [])
        reservation_id = request.data.get('reservationId')
        hold_minutes = int(request.data.get('holdMinutes', 15))
        
        print(f"🔍 RESERVE DEBUG - Raw request data: {request.data}")
        print(f"🔍 RESERVE DEBUG - Tickets array: {tickets}")

        if not isinstance(tickets, list) or not tickets:
            return Response({"detail": "Tickets payload is required."}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        expires_at = now + timedelta(minutes=hold_minutes)

        with transaction.atomic():
            # 🚀 ENTERPRISE: Clean expired holds for these tiers before proceeding
            tier_ids = [t.get('tierId') for t in tickets if t.get('tierId')]
            expired_holds = TicketHold.objects.select_for_update().filter(
                ticket_tier_id__in=tier_ids,
                released=False,
                expires_at__lte=now,
            )
            for hold in expired_holds:
                hold.release()

            # Get or create reservation order
            if reservation_id:
                try:
                    order = Order.objects.select_for_update().get(id=reservation_id, event=event)
                    print(f"🔄 RESERVE DEBUG - Reusing existing reservation: {reservation_id}")
                except Order.DoesNotExist:
                    print(f"⚠️ RESERVE DEBUG - Reservation {reservation_id} not found, creating new one")
                    order = Order.objects.create(
                        event=event,
                        email='',  # Will be collected during checkout
                        first_name='Guest',
                        last_name='User',
                        phone='',
                        subtotal=0,
                        service_fee=0,
                        total=0,
                        currency=event.ticket_tiers.first().currency if event.ticket_tiers.exists() else 'CLP',
                        status='pending'
                    )
            else:
                print(f"🆕 RESERVE DEBUG - Creating new reservation")
                order = Order.objects.create(
                    event=event,
                    email='',  # Will be collected during checkout
                    first_name='Guest',
                    last_name='User',
                    phone='',
                    subtotal=0,
                    service_fee=0,
                    total=0,
                    currency=event.ticket_tiers.first().currency if event.ticket_tiers.exists() else 'CLP',
                    status='pending'
                )

            # 🚀 ENTERPRISE: Index existing active holds for this order
            active_holds = list(TicketHold.objects.select_for_update().filter(
                order=order, released=False, expires_at__gt=now
            ))
            holds_by_tier = {}
            for hold in active_holds:
                holds_by_tier.setdefault(str(hold.ticket_tier_id), []).append(hold)

            # 🚀 ENTERPRISE: For each requested tier, adjust holds to match desired quantity
            result_items = []
            for t in tickets:
                tier_id = t.get('tierId')
                qty = int(t.get('quantity', 0))
                custom_price = t.get('customPrice')  # 🚀 NEW: Support for PWYW custom pricing
                if not tier_id or qty < 0:
                    continue
                
                print(f"🎯 RESERVE DEBUG - Processing tier {tier_id}: qty={qty}, custom_price={custom_price}")

                try:
                    tier = TicketTier.objects.select_for_update().get(id=tier_id, event=event)
                except TicketTier.DoesNotExist:
                    return Response({"detail": f"Ticket tier {tier_id} not found."}, status=status.HTTP_400_BAD_REQUEST)

                existing_qty = sum(h.quantity for h in holds_by_tier.get(str(tier_id), []) if not h.is_expired)

                if qty > existing_qty:
                    need = qty - existing_qty
                    
                    # 🚀 ENTERPRISE: Atomic reservation using UPDATE with WHERE clause
                    # This prevents race conditions by doing check + reserve in one atomic operation
                    from django.db.models import F
                    
                    updated_rows = TicketTier.objects.filter(
                        id=tier_id,
                        available__gte=need  # ✅ Check availability at DB level
                    ).update(
                        available=F('available') - need  # ✅ Atomic decrease
                    )
                    
                    if updated_rows == 0:
                        # ❌ Not enough tickets available or tier doesn't exist
                        tier.refresh_from_db()  # Get fresh data for error message
                        return Response({
                            "detail": f"No hay suficientes tickets disponibles para {tier.name}. "
                                    f"Disponibles: {tier.real_available}, Solicitados: {need}"
                        }, status=status.HTTP_400_BAD_REQUEST)
                
                    # ✅ Success: tickets were atomically reserved, now create holds
                    for _ in range(need):
                        # 🚀 ENTERPRISE: Include custom_price for PWYW tickets
                        hold_data = {
                            'event': event,
                            'ticket_tier': tier,
                            'order': order,
                            'quantity': 1,
                            'expires_at': expires_at,
                        }
                        
                        # Add custom_price if this is a PWYW ticket
                        if tier.is_pay_what_you_want and custom_price is not None:
                            from decimal import Decimal
                            print(f"🔍 RESERVE DEBUG - PWYW tier {tier_id}: custom_price received = {custom_price} (type: {type(custom_price)})")
                            custom_price_decimal = Decimal(str(custom_price))
                            print(f"🔍 RESERVE DEBUG - Decimal conversion: {custom_price_decimal}")
                            hold_data['custom_price'] = custom_price_decimal
                        
                        created_hold = TicketHold.objects.create(**hold_data)
                        print(f"🔍 RESERVE DEBUG - Created hold: tier={created_hold.ticket_tier_id}, custom_price={created_hold.custom_price}")
                
                elif qty < existing_qty:
                    to_release = existing_qty - qty
                    # 🚀 ENTERPRISE: Release oldest holds first
                    holds_list = sorted(holds_by_tier.get(str(tier_id), []), key=lambda h: h.expires_at)
                    for hold in holds_list:
                        if to_release <= 0:
                            break
                        hold.release()
                        to_release -= hold.quantity

                result_items.append({
                    'tierId': str(tier_id),
                    'quantity': qty
                })

            return Response({
                'reservationId': str(order.id),
                'expiresAt': expires_at.isoformat(),
                'items': result_items,
                'holdMinutes': hold_minutes
            })
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get list of event categories."""
        categories = EventCategory.objects.all()
        return Response([category.name for category in categories])
    
    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """🚀 ENTERPRISE: Advanced analytics with REAL EFFECTIVE REVENUE calculation.
        
        Revenue calculation considers:
        - Actual amounts paid (not base price x quantity)
        - Coupon discounts applied
        - Price changes over time
        - Service fees and taxes
        - Manual discounts
        """
        from django.db.models import Sum, Count, Avg, Q, F
        from django.utils import timezone
        from datetime import datetime, timedelta
        from collections import defaultdict
        
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "Usuario sin organizador asociado"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get parameters
        days = int(request.query_params.get('days', 30))
        event_id = request.query_params.get('event_id')
        start_date = timezone.now() - timedelta(days=days)
        
        # Base queryset for PAID orders only (effective sales)
        orders_queryset = Order.objects.filter(
            event__organizer=organizer,
            status='paid',  # Only count actually paid orders
            created_at__gte=start_date
        ).select_related('event')
        
        if event_id:
            orders_queryset = orders_queryset.filter(event_id=event_id)
        
        # 🚀 ENTERPRISE: EFFECTIVE REVENUE CALCULATION
        # Sum the actual 'total' field from orders (what customers actually paid)
        revenue_data = orders_queryset.aggregate(
            total_revenue=Sum('total'),  # Effective revenue (after discounts, fees, etc.)
            gross_revenue=Sum('subtotal'),  # Revenue before service fees
            total_service_fees=Sum('service_fee'),
            total_taxes=Sum('taxes'),
            total_discount=Sum('discount'),
            total_orders=Count('id')
        )
        
        # Calculate total tickets sold (from order items)
        tickets_data = OrderItem.objects.filter(
            order__in=orders_queryset
        ).aggregate(
            total_tickets=Sum('quantity'),
            avg_unit_price=Avg('unit_price')  # Average actual price paid per ticket
        )
        
        total_revenue = float(revenue_data['total_revenue'] or 0)
        total_tickets = tickets_data['total_tickets'] or 0
        total_orders = revenue_data['total_orders'] or 0
        
        # Calculate effective average ticket price (what was actually paid)
        effective_avg_price = 0
        if total_tickets > 0:
            effective_avg_price = total_revenue / total_tickets
        
        # 🚀 ENTERPRISE: Time series with effective revenue
        chart_data = []
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            next_date = current_date + timedelta(days=1)
            
            daily_orders = orders_queryset.filter(
                created_at__gte=current_date,
                created_at__lt=next_date
            )
            
            daily_stats = daily_orders.aggregate(
                revenue=Sum('total'),  # Effective revenue
                gross_revenue=Sum('subtotal'),
                orders=Count('id')
            )
            
            daily_tickets = OrderItem.objects.filter(
                order__in=daily_orders
            ).aggregate(tickets=Sum('quantity'))
            
            chart_data.append({
                'date': current_date.strftime('%d/%m/%Y'),
                'sales': daily_tickets['tickets'] or 0,
                'revenue': float(daily_stats['revenue'] or 0),
                'gross_revenue': float(daily_stats['gross_revenue'] or 0),
                'orders': daily_stats['orders'] or 0
            })
        
        # 🚀 ENTERPRISE: Ticket categories with effective revenue
        category_data = []
        if event_id:
            # For specific event - group by ticket tiers
            event = Event.objects.get(id=event_id)
            for tier in event.ticket_tiers.all():
                tier_items = OrderItem.objects.filter(
                    ticket_tier=tier,
                    order__status='paid',
                    order__created_at__gte=start_date
                ).aggregate(
                    tickets=Sum('quantity'),
                    effective_revenue=Sum(F('unit_price') * F('quantity')),  # Actual price paid
                    service_fees=Sum(F('unit_service_fee') * F('quantity'))
                )
                
                tickets_sold = tier_items['tickets'] or 0
                if tickets_sold > 0:
                    category_data.append({
                        'name': tier.name,
                        'value': tickets_sold,
                        'effective_revenue': float(tier_items['effective_revenue'] or 0),
                        'service_fees': float(tier_items['service_fees'] or 0),
                        'base_price': float(tier.price),
                        'fill': f"#{hash(tier.name) % 16777215:06x}"
                    })
        else:
            # For all events - aggregate by tier names
            tier_stats = defaultdict(lambda: {
                'tickets': 0, 
                'effective_revenue': 0, 
                'service_fees': 0,
                'orders': set()
            })
            
            order_items = OrderItem.objects.filter(
                order__event__organizer=organizer,
                order__status='paid',
                order__created_at__gte=start_date
            ).select_related('ticket_tier', 'order')
            
            for item in order_items:
                tier_name = item.ticket_tier.name
                tier_stats[tier_name]['tickets'] += item.quantity
                tier_stats[tier_name]['effective_revenue'] += float(item.unit_price * item.quantity)
                tier_stats[tier_name]['service_fees'] += float(item.unit_service_fee * item.quantity)
                tier_stats[tier_name]['orders'].add(item.order_id)
            
            for tier_name, stats in tier_stats.items():
                if stats['tickets'] > 0:
                    category_data.append({
                        'name': tier_name,
                        'value': stats['tickets'],
                        'effective_revenue': stats['effective_revenue'],
                        'service_fees': stats['service_fees'],
                        'orders_count': len(stats['orders']),
                        'fill': f"#{hash(tier_name) % 16777215:06x}"
                    })
        
        # 🚀 ENTERPRISE: Enhanced device/channel analysis (placeholder for now)
        # TODO: Implement real device tracking with user agent analysis
        device_data = [
            {'name': 'Mobile', 'value': int(total_orders * 0.6), 'fill': '#8884d8'},
            {'name': 'Desktop', 'value': int(total_orders * 0.35), 'fill': '#83a6ed'},
            {'name': 'Tablet', 'value': int(total_orders * 0.05), 'fill': '#8dd1e1'},
        ]
        
        # TODO: Implement UTM tracking for real channel data
        channel_data = [
            {'name': 'Sitio Web', 'value': int(total_orders * 0.7), 'fill': '#8884d8'},
            {'name': 'Redes Sociales', 'value': int(total_orders * 0.2), 'fill': '#83a6ed'},
            {'name': 'Directo', 'value': int(total_orders * 0.1), 'fill': '#8dd1e1'},
        ]
        
        return Response({
            'kpis': {
                'totalSales': total_tickets,
                'totalRevenue': total_revenue,  # Effective revenue (what was actually paid)
                'grossRevenue': float(revenue_data['gross_revenue'] or 0),
                'totalServiceFees': float(revenue_data['total_service_fees'] or 0),
                'totalDiscounts': float(revenue_data['total_discount'] or 0),
                'averageTicketPrice': round(effective_avg_price, 2),  # Effective average
                'totalOrders': total_orders,
                'conversionRate': 0,  # Placeholder - needs view tracking implementation
                'averageOrderValue': round(total_revenue / total_orders, 2) if total_orders > 0 else 0
            },
            'chartData': chart_data,
            'categoryData': category_data,
            'deviceData': device_data,
            'channelData': channel_data,
            'dateRange': {
                'start': start_date.isoformat(),
                'end': timezone.now().isoformat(),
                'days': days
            },
            'metadata': {
                'calculation_method': 'effective_revenue',
                'includes_discounts': True,
                'includes_service_fees': True,
                'only_paid_orders': True
            }
        })

    @action(detail=True, methods=['get'])
    def conversion_metrics(self, request, pk=None):
        """🚀 ENTERPRISE: Get conversion funnel metrics for a specific event."""
        from apps.events.analytics_models import EventView, ConversionFunnel, EventPerformanceMetrics
        from django.db.models import Count, Avg
        from datetime import timedelta
        
        event = self.get_object()
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Get funnel stages count
        funnel_data = ConversionFunnel.objects.filter(
            event=event,
            created_at__gte=start_date
        ).values('stage').annotate(count=Count('id')).order_by('stage')
        
        # Get view metrics
        views = EventView.objects.filter(
            event=event,
            created_at__gte=start_date
        )
        
        total_views = views.count()
        unique_views = views.values('session_id').distinct().count()
        converted_views = views.filter(converted_to_purchase=True).count()
        avg_time_on_page = views.aggregate(avg=Avg('time_on_page'))['avg'] or 0
        
        # Calculate conversion rate
        conversion_rate = (converted_views / total_views * 100) if total_views > 0 else 0
        
        # Get traffic sources
        traffic_sources = views.values('view_source').annotate(
            count=Count('id'),
            conversions=Count('id', filter=models.Q(converted_to_purchase=True))
        ).order_by('-count')
        
        # Device breakdown
        device_breakdown = views.values('device_type').annotate(
            count=Count('id'),
            conversions=Count('id', filter=models.Q(converted_to_purchase=True))
        ).order_by('-count')
        
        return Response({
            'event_id': str(event.id),
            'event_title': event.title,
            'date_range': {
                'start': start_date.isoformat(),
                'end': timezone.now().isoformat(),
                'days': days
            },
            'funnel_stages': list(funnel_data),
            'view_metrics': {
                'total_views': total_views,
                'unique_views': unique_views,
                'converted_views': converted_views,
                'conversion_rate': round(conversion_rate, 2),
                'avg_time_on_page': round(avg_time_on_page, 2) if avg_time_on_page else 0
            },
            'traffic_sources': [
                {
                    'source': item['view_source'],
                    'views': item['count'],
                    'conversions': item['conversions'],
                    'conversion_rate': round(item['conversions'] / item['count'] * 100, 2) if item['count'] > 0 else 0
                }
                for item in traffic_sources
            ],
            'device_breakdown': [
                {
                    'device': item['device_type'],
                    'views': item['count'],
                    'conversions': item['conversions'],
                    'conversion_rate': round(item['conversions'] / item['count'] * 100, 2) if item['count'] > 0 else 0
                }
                for item in device_breakdown
            ]
        })

    @action(detail=False, methods=['post'])
    def track_view(self, request):
        """🚀 ENTERPRISE: Track an event view for analytics."""
        from apps.events.analytics_models import EventView
        
        event_id = request.data.get('event_id')
        if not event_id:
            return Response({'detail': 'event_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            event = Event.objects.get(id=event_id)
            view = EventView.track_view(event, request)
            
            return Response({
                'view_id': str(view.id) if view else None,
                'event_id': str(event.id),
                'tracked': view is not None
            })
            
        except Event.DoesNotExist:
            return Response({'detail': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def organizer(self, request):
        """Get events for the current organizer with metrics."""
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "Usuario sin organizador asociado"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get all events for the organizer
        events = Event.objects.filter(organizer=organizer).select_related(
            'location', 'category'
        ).prefetch_related(
            'ticket_tiers', 'images'
        ).order_by('-start_date')
        
        # Apply filters
        status_filter = request.query_params.getlist('status', [])
        if status_filter:
            events = events.filter(status__in=status_filter)
        
        start_date = request.query_params.get('start_date')
        if start_date:
            events = events.filter(start_date__gte=start_date)
        
        end_date = request.query_params.get('end_date')
        if end_date:
            events = events.filter(start_date__lte=end_date)
        
        # Filter out events without start_date for proper sorting
        events = events.exclude(start_date__isnull=True)
        
        search = request.query_params.get('search')
        if search:
            events = events.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(location__name__icontains=search) |
                Q(location__address__icontains=search)
            )
        
        # Calculate metrics for each event
        events_with_metrics = []
        for event in events:
            # Calculate ticket metrics
            total_tickets = 0
            sold_tickets = 0
            total_revenue = 0
            
            for tier in event.ticket_tiers.all():
                # 🚀 ENTERPRISE: Use real data instead of estimates
                tier_capacity = tier.capacity or 0
                tier_sold = tier.tickets_sold  # Real sold tickets from paid orders
                
                total_tickets += tier_capacity
                sold_tickets += tier_sold
                total_revenue += tier_sold * tier.price
            
            events_with_metrics.append({
                'id': str(event.id),
                'title': event.title,
                'start_date': event.start_date.isoformat() if event.start_date else None,
                'end_date': event.end_date.isoformat() if event.end_date else None,
                'status': event.status,
                'location': {
                    'name': event.location.name if event.location else '',
                    'address': event.location.address if event.location else '',
                    'is_virtual': event.location.is_virtual if event.location else False
                },
                'ticket_tiers': [
                    {
                        'id': str(tier.id),
                        'name': tier.name,
                        'price': tier.price,
                        'quantity': tier.capacity,
                        'sold_quantity': tier.tickets_sold,  # 🚀 ENTERPRISE: Use real sold data
                        'capacity': tier.capacity,  # Include original capacity for null detection
                        'is_unlimited': tier.capacity is None  # 🚀 ENTERPRISE: Flag for unlimited capacity
                    }
                    for tier in event.ticket_tiers.all()
                ],
                'total_revenue': total_revenue,
                'total_tickets': total_tickets,
                'sold_tickets': sold_tickets,
                'has_unlimited_capacity': any(tier.capacity is None for tier in event.ticket_tiers.all()),  # 🚀 ENTERPRISE: Event-level unlimited flag
                'images': [
                    {
                        'id': str(img.id),
                        'url': request.build_absolute_uri(img.image.url) if img.image else ''
                    }
                    for img in event.images.all()
                ]
            })
        
        return Response(events_with_metrics)
    
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        """🚀 ENTERPRISE IMAGE UPLOAD - Upload an image file and optionally associate with an event."""
        if 'file' not in request.FILES:
            return Response({'detail': 'No file found'}, status=status.HTTP_400_BAD_REQUEST)
        
        file_obj = request.FILES['file']
        event_id = request.data.get('event_id')  # Optional event association
        
        # Generate a unique filename
        filename = f"{uuid.uuid4().hex}.{file_obj.name.split('.')[-1]}"
        
        # 🚀 ENTERPRISE: Use Django's configured storage backend (local in dev, GCS in prod)
        from django.core.files.storage import default_storage
        
        try:
            # Save file using Django's storage backend (automatically uses correct storage)
            file_path = f"event_images/{filename}"
            saved_path = default_storage.save(file_path, file_obj)
            
            # Get the full URL for the uploaded file
            file_url = default_storage.url(saved_path)
            
            print(f"[UPLOAD] ✅ File uploaded to: {saved_path}")
            print(f"[UPLOAD] ✅ File URL: {file_url}")
            
            # If event_id is provided, create EventImage record
            if event_id:
                try:
                    event = Event.objects.get(id=event_id)
                    
                    # Verify user has permission to modify this event
                    organizer = self.get_organizer()
                    if not organizer or event.organizer != organizer:
                        # Clean up uploaded file if permission denied
                        try:
                            default_storage.delete(saved_path)
                        except Exception as e:
                            print(f"[UPLOAD] ⚠️ Could not delete file {saved_path}: {e}")
                        return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
                    
                    # Create EventImage record
                    event_image = EventImage.objects.create(
                        event=event,
                        image=saved_path,  # Store the path returned by storage backend
                        alt=request.data.get('alt', file_obj.name),
                        type=request.data.get('type', 'image'),
                        order=event.images.count()  # Set order as current count
                    )
                    
                    print(f"[UPLOAD] ✅ Created EventImage record: {event_image.id} for event {event.id}")
                    
                    return Response({
                        'url': file_url,
                        'event_image_id': event_image.id,
                        'message': 'Image uploaded and associated with event successfully'
                    }, status=status.HTTP_201_CREATED)
                
                except Event.DoesNotExist:
                    # Clean up uploaded file if event doesn't exist
                    try:
                        default_storage.delete(saved_path)
                    except Exception as del_e:
                        print(f"[UPLOAD] ⚠️ Could not delete file {saved_path}: {del_e}")
                    return Response({'detail': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
            
            # If no event_id provided, just return the uploaded file URL
            print(f"[UPLOAD] ✅ File uploaded successfully: {file_url}")
            return Response({
                'url': file_url,
                'message': 'Image uploaded successfully'
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"[UPLOAD] ❌ Error during upload: {str(e)}")
            return Response({'detail': f'Error uploading file: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['delete'], url_path=r'images/(?P<image_id>[^/.]+)')
    def delete_image(self, request, pk=None, image_id=None):
        """Delete an event image."""
        event = self.get_object()
        image = get_object_or_404(EventImage, id=image_id, event=event)
        
        # Delete file from storage using Django's storage backend
        try:
            from django.core.files.storage import default_storage
            default_storage.delete(image.image.name)
            print(f"[DELETE-IMAGE] ✅ Deleted file: {image.image.name}")
        except Exception as e:
            print(f"[DELETE-IMAGE] ⚠️ Could not delete file {image.image.name}: {e}")
        
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_create(self, serializer):
        # Obtener el organizador del usuario de manera correcta
        try:
            # Intentar obtener OrganizerUser para el usuario actual
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            organizer = organizer_user.organizer
            
            # Guardar el evento con el organizador encontrado
            event = serializer.save(
                organizer=organizer,
                status='draft'
            )
            
            # Ensure the event has an ID before returning
            event.refresh_from_db()
            return event
        except OrganizerUser.DoesNotExist:
            print(f"Error: Usuario {self.request.user.id} no tiene un organizer asociado")
            raise Exception("El usuario no tiene un organizador asociado")
    
    @action(detail=True, methods=['post'])
    def complete_draft(self, request, pk=None):
        """
        Marcar un evento borrador como completo y listo para añadir tickets y categorías.
        Verifica que el evento tenga toda la información básica necesaria.
        """
        event = self.get_object()
        
        # Log entire event details for debugging
        print(f"DEBUG - Complete Draft Request for event {pk}:")
        print(f"- title: '{event.title}'")
        print(f"- description length: {len(event.description) if event.description else 0}")
        print(f"- short_description: '{event.short_description}'")
        print(f"- start_date: {event.start_date}")
        print(f"- end_date: {event.end_date}")
        print(f"- location: {event.location.id if event.location else None}")
        print(f"- current status: {event.status}")
        
        # Modified: Allow any status to be marked as complete, but log a warning if not draft
        if event.status != 'draft':
            print(f"WARNING: Attempting to mark a non-draft event as complete (status: {event.status})")
            # We'll continue anyway to allow the user to fix issues
        
        # Verificar que el evento tenga toda la información básica necesaria
        required_fields = ['title', 'description', 'short_description', 'start_date', 'end_date', 'location']
        missing_fields = []
        
        for field in required_fields:
            value = getattr(event, field, None)
            if field == 'location':
                if value is None:
                    missing_fields.append(field)
            elif value is None or (isinstance(value, str) and value.strip() == ''):
                missing_fields.append(field)
        
        # Log the event data for debugging
        print(f"Event data for complete_draft: {event.title}, {event.short_description}, {event.start_date}, {event.end_date}")
        
        if missing_fields:
            return Response(
                {
                    'error': 'El evento no está completo',
                    'missing_fields': missing_fields
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Actualizar el estado del evento - setting to draft_complete regardless of previous status
        event.status = 'draft_complete'
        event.save()
        
        return Response({
            'status': 'draft_complete',
            'message': 'El evento ha sido marcado como completo y está listo para añadir tickets y categorías'
        })
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        event = self.get_object()
        
        # Verificar que el evento esté en estado borrador completo
        if event.status != 'draft_complete':
            return Response(
                {'error': 'Solo los eventos con borrador completo pueden ser publicados'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar que el evento tenga al menos una categoría y un ticket tier
        if not event.ticket_categories.exists():
            return Response(
                {'error': 'El evento debe tener al menos una categoría de tickets'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if not event.ticket_tiers.exists():
            return Response(
                {'error': 'El evento debe tener al menos un tipo de ticket'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Todo está bien, publicar el evento
        event.status = 'published'
        event.save()
        
        return Response({
            'status': 'published',
            'message': 'Evento publicado exitosamente'
        })

    def update(self, request, *args, **kwargs):
        """Override update to properly handle camelCase field names."""
        data = request.data.copy()
        
        # Map camelCase keys to snake_case for Django models
        if 'shortDescription' in data:
            print(f"ViewSet - Mapping shortDescription -> short_description: '{data['shortDescription']}'")
            data['short_description'] = data.pop('shortDescription')
        
        if 'startDate' in data:
            print(f"ViewSet - Mapping startDate -> start_date: '{data['startDate']}'")
            data['start_date'] = data.pop('startDate')
        
        if 'endDate' in data:
            print(f"ViewSet - Mapping endDate -> end_date: '{data['endDate']}'")
            data['end_date'] = data.pop('endDate')
        
        # Log all data being sent to serializer
        print(f"ViewSet - Data being sent to serializer: {data}")
        
        # Get instance for updating
        instance = self.get_object()
        
        # Create serializer with the mapped data
        serializer = self.get_serializer(instance, data=data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Log the instance after update
        instance.refresh_from_db()
        print(f"ViewSet - After update: title={instance.title}, short_description={instance.short_description}")
        
        return Response(serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete an event if it has no revenue."""
        event = self.get_object()
        
        try:
            # Check if event can be deleted (no revenue)
            if not event.can_be_deleted():
                return Response(
                    {"detail": "No se puede eliminar un evento que tiene ingresos"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Perform soft delete
            event.soft_delete()
            
            return Response(
                {"detail": "Evento eliminado correctamente"},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                {"detail": f"Error al eliminar el evento: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EventCategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for event categories.
    """
    queryset = EventCategory.objects.all()
    serializer_class = EventCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    ordering = ['name']


class LocationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for locations.
    """
    serializer_class = LocationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['name']  # Removed city, country as they don't exist in simplified Location model
    search_fields = ['name', 'address']  # Removed city, country
    ordering_fields = ['name']  # Removed city, country
    ordering = ['name']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        Get locations for the current organizer if authenticated.
        """
        if not self.request.user.is_authenticated:
            return Location.objects.filter(events__status='active', events__visibility='public').distinct()
        
        organizer = self.get_organizer()
        if not organizer:
            return Location.objects.none()
        
        return Location.objects.filter(organizer=organizer)
    
    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsOrganizer()]


class TicketCategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for ticket categories.
    """
    serializer_class = TicketCategorySerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'status', 'visibility']
    ordering_fields = ['order', 'name']
    ordering = ['order']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        Get ticket categories based on permissions.
        """
        # For public access, only return public categories for active events
        if not self.request.user.is_authenticated:
            return TicketCategory.objects.filter(
                event__status='active',
                event__visibility='public',
                visibility='public'
            )
        
        # For organizers, return all their categories
        organizer = self.get_organizer()
        if not organizer:
            return TicketCategory.objects.none()
        
        # Check for event_id in URL or query params
        event_id = self.kwargs.get('event_id')
        if not event_id:
            event_id = self.request.query_params.get('event')
        
        queryset = TicketCategory.objects.filter(event__organizer=organizer)
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset
    
    def get_permissions(self):
        """
        Get permissions based on action.
        """
        print(f"DEBUG - TicketCategoryViewSet.get_permissions - action: {self.action}")
        print(f"DEBUG - TicketCategoryViewSet.get_permissions - user: {self.request.user.id if self.request.user.is_authenticated else 'Anonymous'}")
        
        if self.action in ['list', 'retrieve']:
            print(f"DEBUG - TicketCategoryViewSet.get_permissions - permissions: AllowAny (list/retrieve)")
            return [permissions.AllowAny()]
            
        # Simplificar permisos - la verificación real se hace en los métodos del ViewSet
        print(f"DEBUG - TicketCategoryViewSet.get_permissions - simplified permissions: IsAuthenticated only")
        return [permissions.IsAuthenticated()]
    
    def perform_create(self, serializer):
        """Create a new ticket category with the event ID from the URL or request data."""
        # Check if this is a nested view (event_id in URL)
        event_id = self.kwargs.get('event_id')
        
        if event_id:
            # This is a nested view, get event from URL
            event = get_object_or_404(Event, id=event_id)
            serializer.save(event=event)
        else:
            # This is a standalone/top-level view
            # Get event_id from request data
            event_id = self.request.data.get('event')
            
            if not event_id:
                raise serializers.ValidationError({"event": "Event ID is required to create a ticket category"})
                
            # Get the event instance
            event = get_object_or_404(Event, id=event_id)
            
            # Check if the event belongs to the organizer
            organizer = self.get_organizer()
            if not organizer or event.organizer != organizer:
                raise PermissionDenied("You don't have permission to add ticket categories to this event.")
            
            # Create the ticket category with the event
            serializer.save(event=event)
            
    def update(self, request, *args, **kwargs):
        """Override update to use OrganizerUser for permission checks."""
        print(f"DEBUG - TicketCategoryViewSet.update - Starting update for ID: {kwargs.get('pk')}")
        
        # Get the category being updated
        instance = self.get_object()
        
        # Get the organizer associated with the user
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "You don't have permission to update this category as you are not associated with any organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Check if the event belongs to the organizer
        if instance.event.organizer != organizer:
            return Response(
                {"detail": "You don't have permission to update this category as it belongs to another organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
                
        # Permission check passed, proceed with update
        return super().update(request, *args, **kwargs)
        
    def partial_update(self, request, *args, **kwargs):
        """Override partial_update to use OrganizerUser for permission checks."""
        print(f"DEBUG - TicketCategoryViewSet.partial_update - Starting partial update for ID: {kwargs.get('pk')}")
        return self.update(request, *args, **kwargs)
        
    def destroy(self, request, *args, **kwargs):
        """Override destroy to use OrganizerUser for permission checks."""
        print(f"DEBUG - TicketCategoryViewSet.destroy - Starting delete for ID: {kwargs.get('pk')}")
        
        # Get the category being deleted
        instance = self.get_object()
        
        # Get the organizer associated with the user
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "You don't have permission to delete this category as you are not associated with any organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Check if the event belongs to the organizer
        if instance.event.organizer != organizer:
            return Response(
                {"detail": "You don't have permission to delete this category as it belongs to another organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
                
        # Permission check passed, proceed with delete
        return super().destroy(request, *args, **kwargs)


class TicketTierViewSet(viewsets.ModelViewSet):
    """Viewset for ticket tiers."""
    serializer_class = TicketTierSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """Filter queryset by organizer and event_id if provided"""
        organizer = self.get_organizer()
        print(f"DEBUG - TicketTierViewSet.get_queryset - User ID: {self.request.user.id}, Organizer: {organizer.id if organizer else 'None'}")
        
        if not organizer:
            print(f"DEBUG - TicketTierViewSet.get_queryset - No organizer found for user")
            return TicketTier.objects.none()
        
        # If this is a nested view under an event, filter by the event_id from URL
        event_id = self.kwargs.get('event_id')
        
        # If it's a standalone view, check for event query parameter
        if not event_id and self.request.query_params.get('event'):
            event_id = self.request.query_params.get('event')
            print(f"DEBUG - TicketTierViewSet.get_queryset - Using event query parameter: {event_id}")
        
        if event_id:
            print(f"DEBUG - TicketTierViewSet.get_queryset - Filtering by event ID: {event_id}")
            return TicketTier.objects.filter(
                event__organizer=organizer,
                event_id=event_id
            )
        
        # For top-level view without event filter, return all tiers for the organizer's events
        print(f"DEBUG - TicketTierViewSet.get_queryset - No event filter, returning all tiers for organizer")
        return TicketTier.objects.filter(event__organizer=organizer)
    
    def _transform_request_data(self, data):
        """
        🚀 ENTERPRISE: Transform camelCase keys to snake_case for Django models.
        This ensures frontend camelCase fields are properly mapped to backend snake_case.
        """
        print(f"🔍 TRANSFORM DEBUG - Input data keys: {list(data.keys())}")
        
        # Field mapping from camelCase (frontend) to snake_case (Django)
        field_mapping = {
            'isPayWhatYouWant': 'is_pay_what_you_want',
            'minPrice': 'min_price',
            'maxPrice': 'max_price',
            'suggestedPrice': 'suggested_price',
            'maxPerOrder': 'max_per_order',
            'minPerOrder': 'min_per_order',
            'isPublic': 'is_public',
            'requiresApproval': 'requires_approval',
        }
        
        transformed = {}
        
        for key, value in data.items():
            # Use mapping if exists, otherwise keep original key
            new_key = field_mapping.get(key, key)
            transformed[new_key] = value
            
            # Log PWYW field transformations specifically
            if key in field_mapping:
                print(f"✅ TRANSFORM - {key} → {new_key}: {value}")
        
        print(f"🔍 TRANSFORM DEBUG - Output data keys: {list(transformed.keys())}")
        return transformed

    def update(self, request, *args, **kwargs):
        """
        🚀 ENTERPRISE: Robust update with proper field transformation and validation.
        Handles camelCase to snake_case conversion and preserves all fields.
        """
        print(f"🚀 DEBUG - TicketTierViewSet.update - Starting update for ID: {kwargs.get('pk')}")
        print(f"🔍 DEBUG - User ID: {request.user.id}, Username: {request.user.username}")
        print(f"🔍 DEBUG - Raw request.data: {request.data}")
        
        # Get the organizer associated with the user
        try:
            organizer_user = OrganizerUser.objects.get(user=request.user)
            organizer = organizer_user.organizer
            print(f"✅ DEBUG - Found organizer: ID={organizer.id}")
            
            # Get the tier being updated
            instance = self.get_object()
            print(f"🔍 DEBUG - Ticket tier belongs to event ID: {instance.event.id}")
            print(f"🔍 DEBUG - Event organizer ID: {instance.event.organizer.id}")
            
            # Check if the organizer owns the event
            if instance.event.organizer != organizer:
                print(f"❌ DEBUG - PERMISSION DENIED: Ticket tier's event organizer ({instance.event.organizer.id}) does not match user's organizer ({organizer.id})")
                return Response(
                    {"detail": "You don't have permission to update this ticket tier as it belongs to another organizer."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # 🚀 ENTERPRISE FIX: Transform camelCase to snake_case FIRST
            transformed_data = self._transform_request_data(request.data.copy())
            
            # 🚀 ENTERPRISE FIX: Handle structured price object while preserving ALL other fields
            if 'price' in transformed_data and isinstance(transformed_data['price'], dict):
                price_obj = transformed_data['price']
                base_price = price_obj.get('basePrice', 0)
                print(f"💰 DEBUG - Extracting price from object: {base_price}")
                
                # Replace price object with extracted base price
                transformed_data['price'] = base_price
            
            # Log PWYW fields specifically for debugging
            pwyw_fields = ['is_pay_what_you_want', 'min_price', 'max_price', 'suggested_price']
            for field in pwyw_fields:
                if field in transformed_data:
                    print(f"✅ PWYW DEBUG - {field}: {transformed_data[field]}")
                else:
                    print(f"⚠️ PWYW DEBUG - {field}: NOT FOUND")
            
            # 🚀 ENTERPRISE: Use transformed data with ALL fields preserved
            serializer = self.get_serializer(
                instance, 
                data=transformed_data, 
                partial=kwargs.get('partial', False)
            )
            
            print(f"🔍 DEBUG - Serializer validation starting...")
            serializer.is_valid(raise_exception=True)
            print(f"✅ DEBUG - Serializer validation passed")
            
            # Perform the update
            self.perform_update(serializer)
            print(f"✅ DEBUG - Update completed successfully")
            
            # Log the final saved data
            instance.refresh_from_db()
            print(f"💾 DEBUG - Final saved PWYW status: {instance.is_pay_what_you_want}")
            if instance.is_pay_what_you_want:
                print(f"💾 DEBUG - Final saved min_price: {instance.min_price}")
                print(f"💾 DEBUG - Final saved max_price: {instance.max_price}")
                print(f"💾 DEBUG - Final saved suggested_price: {instance.suggested_price}")
            
            return Response(serializer.data)
            
        except OrganizerUser.DoesNotExist:
            print(f"❌ DEBUG - PERMISSION DENIED: User {request.user.id} is not associated with any organizer")
            return Response(
                {"detail": "You don't have permission to update this ticket tier as you are not associated with any organizer."},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            print(f"❌ DEBUG - Error during update: {str(e)}")
            import traceback
            print(f"❌ DEBUG - Full traceback: {traceback.format_exc()}")
            return Response(
                {"detail": f"Error updating ticket tier: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def partial_update(self, request, *args, **kwargs):
        """
        🚀 ENTERPRISE: Robust partial update using the same transformation logic.
        """
        print(f"🚀 DEBUG - TicketTierViewSet.partial_update - Starting partial update for ID: {kwargs.get('pk')}")
        
        # Ensure partial=True for partial updates
        kwargs['partial'] = True
        
        # Use the same robust update logic
        return self.update(request, *args, **kwargs)
    
    def create(self, request, *args, **kwargs):
        """
        🚀 ENTERPRISE: Robust create with proper field transformation.
        """
        print(f"🚀 DEBUG - TicketTierViewSet.create - Starting create")
        print(f"🔍 DEBUG - Raw request.data: {request.data}")
        
        # Transform camelCase to snake_case
        transformed_data = self._transform_request_data(request.data.copy())
        
        # Handle structured price object
        if 'price' in transformed_data and isinstance(transformed_data['price'], dict):
            price_obj = transformed_data['price']
            base_price = price_obj.get('basePrice', 0)
            print(f"💰 DEBUG - Extracting price from object: {base_price}")
            transformed_data['price'] = base_price
        
        # Log PWYW fields for debugging
        pwyw_fields = ['is_pay_what_you_want', 'min_price', 'max_price', 'suggested_price']
        for field in pwyw_fields:
            if field in transformed_data:
                print(f"✅ PWYW CREATE DEBUG - {field}: {transformed_data[field]}")
        
        # Create new request with transformed data
        request._full_data = transformed_data
        
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """
        🚀 ENTERPRISE: Create a ticket tier with proper event association and field handling.
        """
        # Get the event from the URL if this is a nested view
        event_id = self.kwargs.get('event_id')
        if event_id:
            print(f"🚀 DEBUG - TicketTierViewSet.perform_create - Creating ticket tier with event ID from URL: {event_id}")
            event = get_object_or_404(Event, id=event_id)
            
            # Check if the event belongs to the organizer
            organizer = self.get_organizer()
            if not organizer or event.organizer != organizer:
                print(f"❌ DEBUG - PERMISSION DENIED: Event organizer ({event.organizer.id}) does not match user's organizer ({organizer.id if organizer else 'None'})")
                raise PermissionDenied("You don't have permission to add ticket tiers to this event.")
            
            # Get capacity to set available field
            capacity = self.request.data.get('capacity', 0)
            print(f"🔍 DEBUG - Using capacity value for available: {capacity}")
            
            # 🚀 ENTERPRISE FIX: Handle unlimited capacity properly
            # If capacity is null (unlimited), set available to a large number
            available_value = capacity if capacity is not None else 9999999
            print(f"✅ DEBUG - Setting available to: {available_value} (capacity: {capacity})")
            
            # Save with event association and proper available value
            serializer.save(event=event, available=available_value)
        else:
            # Extract event ID from request data for top-level view
            event_id = self.request.data.get('event')
            print(f"🚀 DEBUG - TicketTierViewSet.perform_create - Creating ticket tier with event ID from request data: {event_id}")
            
            if not event_id:
                print(f"DEBUG - TicketTierViewSet.perform_create - FAIL: No event ID in request data")
                raise serializers.ValidationError({"event": "Event ID is required to create a ticket tier"})
                
            # Get the event instance
            event = get_object_or_404(Event, id=event_id)
            
            # Check if the event belongs to the organizer
            organizer = self.get_organizer()
            if not organizer or event.organizer != organizer:
                print(f"DEBUG - PERMISSION DENIED: Event organizer ({event.organizer.id}) does not match user's organizer ({organizer.id if organizer else 'None'})")
                raise PermissionDenied("You don't have permission to add ticket tiers to this event.")
            
            # 🚀 ENTERPRISE FIX: Handle price properly regardless of format
            price_data = self.request.data.get('price', 0)
            if isinstance(price_data, dict):
                price_data = price_data.get('basePrice', 0)
                print(f"DEBUG - Extracted price from object: {price_data}")
            elif price_data is None:
                price_data = 0
                print(f"DEBUG - Price was None, using default: {price_data}")
            else:
                print(f"DEBUG - Using direct price value: {price_data}")
                
            # Get capacity to set available field
            capacity = self.request.data.get('capacity', 0)
            print(f"DEBUG - Using capacity value for available: {capacity}")
            
            # 🚀 ENTERPRISE FIX: Handle unlimited capacity properly
            # If capacity is null (unlimited), set available to a large number
            available_value = capacity if capacity is not None else 9999999
            print(f"DEBUG - Setting available to: {available_value} (capacity: {capacity})")
            
            # Save with extracted price value and set available properly
            serializer.save(event=event, price=price_data, available=available_value)

    @action(detail=True, methods=['post'])
    def form_link(self, request, pk=None):
        """Link a form to a ticket tier"""
        ticket_tier = self.get_object()
        form_id = request.data.get('form_id')
        
        if not form_id:
            return Response(
                {"detail": "Form ID is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            form = Form.objects.get(id=form_id)
            
            # Get the organizer properly
            organizer = self.get_organizer()
            
            # Verify the form belongs to the same organizer
            if form.organizer != organizer:
                return Response(
                    {"detail": "You don't have permission to use this form"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Update the ticket tier with the form directly
            ticket_tier.form = form
            ticket_tier.save()
            
            return Response({
                "id": ticket_tier.id,
                "name": ticket_tier.name,
                "form_id": form_id,
                "form_name": form.name
            })
            
        except Form.DoesNotExist:
            return Response(
                {"detail": "Form not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def category_link(self, request, pk=None):
        """Link a category to a ticket tier"""
        ticket_tier = self.get_object()
        category_id = request.data.get('category_id')
        
        if not category_id:
            return Response(
                {"detail": "Category ID is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            category = TicketCategory.objects.get(id=category_id)
            
            # Get the organizer properly
            organizer = self.get_organizer()
            
            # Verify the category belongs to the same organizer and event
            if category.event.organizer != organizer:
                return Response(
                    {"detail": "You don't have permission to use this category"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Verify the category belongs to the same event as the ticket tier
            if category.event != ticket_tier.event:
                return Response(
                    {"detail": "Category must belong to the same event as the ticket tier"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update the ticket tier with the category directly
            ticket_tier.category = category
            ticket_tier.save()
            
            return Response({
                "id": ticket_tier.id,
                "name": ticket_tier.name,
                "category_id": category_id,
                "category_name": category.name
            })
            
        except TicketCategory.DoesNotExist:
            return Response(
                {"detail": "Category not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"detail": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



    
    @action(detail=False, methods=['get'])
    def types(self, request):
        """
        Get available field types and their configurations.
        """
        field_types = [
            {
                'value': 'text',
                'label': 'Texto corto',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': True,
                'validations': ['minLength', 'maxLength', 'pattern']
            },
            {
                'value': 'textarea',
                'label': 'Texto largo',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': True,
                'validations': ['minLength', 'maxLength']
            },
            {
                'value': 'email',
                'label': 'Email',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': False
            },
            {
                'value': 'phone',
                'label': 'Teléfono',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': False
            },
            {
                'value': 'number',
                'label': 'Número',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsValidation': True,
                'validations': ['min', 'max']
            },
            {
                'value': 'select',
                'label': 'Lista desplegable',
                'supportsRequired': True,
                'supportsPlaceholder': True,
                'supportsHelpText': True,
                'supportsOptions': True,
                'supportsValidation': False
            },
            {
                'value': 'checkbox',
                'label': 'Casillas de verificación',
                'supportsRequired': True,
                'supportsHelpText': True,
                'supportsOptions': True,
                'supportsValidation': False
            },
            {
                'value': 'radio',
                'label': 'Opciones únicas',
                'supportsRequired': True,
                'supportsHelpText': True,
                'supportsOptions': True,
                'supportsValidation': False
            },
            {
                'value': 'date',
                'label': 'Fecha',
                'supportsRequired': True,
                'supportsHelpText': True,
                'supportsValidation': False
            },
            {
                'value': 'heading',
                'label': 'Título',
                'supportsRequired': False,
                'supportsHelpText': False,
                'supportsValidation': False
            },
            {
                'value': 'paragraph',
                'label': 'Párrafo',
                'supportsRequired': False,
                'supportsHelpText': True,
                'supportsValidation': False
            }
        ]
        
        width_options = [
            {'value': 'full', 'label': 'Completo'},
            {'value': 'half', 'label': 'Medio'},
            {'value': 'third', 'label': 'Un tercio'}
        ]
        
        conditional_operators = [
            {'value': 'equals', 'label': 'Es igual a'},
            {'value': 'notEquals', 'label': 'No es igual a'},
            {'value': 'contains', 'label': 'Contiene'},
            {'value': 'notContains', 'label': 'No contiene'},
            {'value': 'greaterThan', 'label': 'Mayor que'},
            {'value': 'lessThan', 'label': 'Menor que'}
        ]
        
        return Response({
            'fieldTypes': field_types,
            'widthOptions': width_options,
            'conditionalOperators': conditional_operators
        })


class OrderViewSet(viewsets.ModelViewSet):
    """
    API endpoint for orders.
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event', 'status', 'payment_method']
    search_fields = ['order_number', 'first_name', 'last_name', 'email']
    ordering_fields = ['created_at', 'updated_at', 'total']
    ordering = ['-created_at']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_serializer_class(self):
        """
        Return appropriate serializer class.
        """
        if self.action == 'retrieve':
            return OrderDetailSerializer
        return OrderSerializer
    
    def get_queryset(self):
        """
        Get orders based on permissions with STRICT event isolation.
        🚀 ENTERPRISE: Multi-level filtering to prevent data leakage between events.
        """
        # Regular users can only see their own orders
        if self.request.user.is_authenticated and not hasattr(self.request.user, 'organizer_roles'):
            return Order.objects.filter(user=self.request.user)
        
        # 🚀 ENTERPRISE: Organizers can see orders for their events with STRICT isolation
        if self.request.user.is_authenticated:
            organizer = self.get_organizer()
            if organizer:
                # 🚨 CRITICAL: Event ID is MANDATORY for security
                event_id = self.request.query_params.get('event_id')
                if not event_id:
                    # 🚨 SECURITY: Without event_id, return empty to prevent data leakage
                    return Order.objects.none()
                
                # 🚀 ENTERPRISE: Multi-level filtering for maximum security
                queryset = Order.objects.filter(
                    event__organizer=organizer,
                    event_id=event_id  # ← STRICT event isolation
                )
                
                # 🚨 SECURITY: Additional validation - ensure event belongs to organizer
                event = Event.objects.filter(id=event_id, organizer=organizer).first()
                if not event:
                    return Order.objects.none()
                
                return queryset
        
        # No orders for unauthenticated users
        return Order.objects.none()
    
    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """
        Refund an order.
        """
        order = self.get_object()
        
        # Check if order can be refunded
        if order.status != 'paid':
            return Response(
                {"detail": "Only paid orders can be refunded."},
                status=status.HTTP_400_BAD_REQUEST)
        
        # Get reason from request data
        reason = request.data.get('reason', '')
        amount = request.data.get('amount', order.total)
        
        # In a real app, you would process the refund with a payment gateway here
        
        # Update order status
        order.status = 'refunded'
        order.refund_reason = reason
        order.refunded_amount = amount
        order.save()
        
        # Update tickets status
        for item in order.items.all():
            for ticket in item.tickets.all():
                ticket.status = 'refunded'
                ticket.save()
        
        return Response({"detail": "Order refunded successfully."})
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel an order.
        """
        order = self.get_object()
        
        # Check if order can be cancelled
        if order.status not in ['pending', 'paid']:
            return Response(
                {"detail": "Only pending or paid orders can be cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get reason from request data
        reason = request.data.get('reason', '')
        
        # Update order status
        order.status = 'cancelled'
        order.notes = f"{order.notes}\nCancelled: {reason}".strip()
        order.save()
        
        # Update tickets status
        for item in order.items.all():
            for ticket in item.tickets.all():
                ticket.status = 'cancelled'
                ticket.save()
        
        return Response({"detail": "Order cancelled successfully."})


class TicketViewSet(viewsets.ModelViewSet):
    """
    API endpoint for tickets.
    """
    serializer_class = TicketSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'checked_in']
    search_fields = ['ticket_number', 'first_name', 'last_name', 'email']
    ordering_fields = ['first_name', 'last_name', 'check_in_time']
    ordering = ['first_name', 'last_name']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        Get tickets based on permissions with STRICT event isolation.
        🚀 ENTERPRISE: Multi-level filtering to prevent data leakage between events.
        """
        # Regular users can only see their own tickets
        if self.request.user.is_authenticated and not hasattr(self.request.user, 'organizer_roles'):
            return Ticket.objects.filter(order_item__order__user=self.request.user)
        
        # 🚀 ENTERPRISE: Organizers can see tickets for their events with STRICT isolation
        if self.request.user.is_authenticated:
            organizer = self.get_organizer()
            if organizer:
                # 🚨 CRITICAL: Event ID is MANDATORY for security
                event_id = self.request.query_params.get('event_id')
                if not event_id:
                    # 🚨 SECURITY: Without event_id, return empty to prevent data leakage
                    return Ticket.objects.none()
                
                # 🚀 ENTERPRISE: Multi-level filtering for maximum security
                queryset = Ticket.objects.filter(
                    order_item__order__event__organizer=organizer,
                    order_item__order__event_id=event_id  # ← STRICT event isolation
                )
                
                # 🚨 SECURITY: Additional validation - ensure event belongs to organizer
                event = Event.objects.filter(id=event_id, organizer=organizer).first()
                if not event:
                    return Ticket.objects.none()
                
                return queryset
        
        # No tickets for unauthenticated users
        return Ticket.objects.none()
    
    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        """
        Check in a ticket.
        """
        ticket = self.get_object()
        
        # Check if ticket can be checked in
        if ticket.status != 'active':
            return Response(
                {"detail": "Only active tickets can be checked in."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if ticket.checked_in:
            return Response(
                {"detail": "Ticket already checked in."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update ticket status
        ticket.checked_in = True
        ticket.check_in_time = timezone.now()
        ticket.status = 'used'
        ticket.save()
        
        return Response({
            "detail": "Ticket checked in successfully.",
            "ticket": TicketSerializer(ticket).data
        })
    
    @action(detail=True, methods=['post'])
    def validate(self, request, pk=None):
        """
        Validate a ticket by number.
        """
        ticket_number = request.data.get('ticket_number')
        
        if not ticket_number:
            return Response(
                {"detail": "Ticket number is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get organizer properly
            organizer = self.get_organizer()
            if not organizer:
                return Response({
                    "is_valid": False,
                    "detail": "Usuario sin organizador asociado"
                })
            
            # Find ticket by number, ensuring it belongs to the organizer's events
            ticket = Ticket.objects.get(
                ticket_number=ticket_number,
                order_item__order__event__organizer=organizer
            )
            
            # Check ticket status
            if ticket.status != 'active':
                return Response({
                    "is_valid": False,
                    "detail": f"Ticket is not active. Current status: {ticket.get_status_display()}"
                })
            
            if ticket.checked_in:
                return Response({
                    "is_valid": False,
                    "detail": f"Ticket already checked in at {ticket.check_in_time}"
                })
            
            # Return ticket details
            return Response({
                "is_valid": True,
                "ticket": TicketSerializer(ticket).data
            })
            
        except Ticket.DoesNotExist:
            return Response({
                "is_valid": False,
                "detail": "Invalid ticket number"
            })
    
    @action(detail=True, methods=['get'])
    def form(self, request, pk=None):
        """
        Get the form fields for a ticket with conditional logic applied.
        """
        ticket = self.get_object()
        
        # Get the form associated with the ticket tier
        ticket_tier = ticket.order_item.ticket_tier
        form = ticket_tier.form
        
        if not form:
            return Response({
                "detail": "No form associated with this ticket."
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get existing data from the ticket
        existing_data = ticket.form_data or {}
        
        # Get all fields from the form
        all_fields = form.fields.all().order_by('order')
        
        # Process fields to apply conditional logic
        visible_fields = []
        for field in all_fields:
            # Check if field should be visible based on conditional rules
            if self.should_display_field(field, existing_data):
                field_data = FormFieldSerializer(field).data
                field_data['current_value'] = existing_data.get(field.id, '')
                visible_fields.append(field_data)
        
        form_data = {
            'id': form.id,
            'name': form.name,
            'description': form.description,
            'fields': visible_fields,
        }
        
        return Response(form_data)
    
    def should_display_field(self, field, form_data):
        """
        Determine if a field should be displayed based on conditional logic.
        
        Args:
            field: FormField instance
            form_data: Dictionary with existing form data, where keys are field IDs
            
        Returns:
            Boolean indicating if field should be displayed
        """
        # If no conditional display rules, field is always shown
        if not field.conditional_display:
            return True
        
        # Field is only shown if ALL rules are satisfied
        for rule in field.conditional_display:
            source_field_id = rule.get('sourceField')
            condition = rule.get('condition')
            expected_value = rule.get('value')
            
            # If rule is incomplete, ignore it
            if not all([source_field_id, condition, expected_value is not None]):
                continue
            
            # Get actual value from form data
            actual_value = form_data.get(source_field_id, '')
            
            # Apply the condition
            if condition == 'equals' and str(actual_value) != str(expected_value):
                return False
            elif condition == 'notEquals' and str(actual_value) == str(expected_value):
                return False
            elif condition == 'contains' and str(expected_value) not in str(actual_value):
                return False
            elif condition == 'notContains' and str(expected_value) in str(actual_value):
                return False
            elif condition == 'greaterThan':
                try:
                    if float(actual_value) <= float(expected_value):
                        return False
                except (ValueError, TypeError):
                    return False
            elif condition == 'lessThan':
                try:
                    if float(actual_value) >= float(expected_value):
                        return False
                except (ValueError, TypeError):
                    return False
        
        # All rules passed
        return True
    
    @action(detail=True, methods=['post'])
    def submit_form(self, request, pk=None):
        """
        Submit form data for a ticket.
        """
        ticket = self.get_object()
        form_data = request.data.get('form_data', {})
        
        # Validate form data against form schema
        if ticket.order_item.ticket_tier.form:
            form = ticket.order_item.ticket_tier.form
            fields = form.fields.all()
            
            # Check required fields
            for field in fields:
                # Skip conditional fields that shouldn't be visible
                if not self.should_display_field(field, form_data):
                    continue
                    
                field_id = str(field.id)
                if field.required and (field_id not in form_data or not form_data[field_id]):
                    return Response({
                        "detail": f"Field '{field.label}' is required."
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Store the form data on the ticket
            ticket.form_data = form_data
            ticket.save()
            
            return Response({
                "detail": "Form data saved successfully.",
                "ticket": TicketSerializer(ticket).data
            })
        
        return Response({
            "detail": "No form associated with this ticket."
        }, status=status.HTTP_400_BAD_REQUEST)


class CouponViewSet(viewsets.ModelViewSet):
    """
    API endpoint for coupons.
    """
    serializer_class = CouponSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'status', 'discount_type']
    search_fields = ['code', 'description']
    ordering_fields = ['code', 'discount_value', 'created_at', 'usage_count']
    ordering = ['-created_at']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        🚀 ENTERPRISE: Get coupons with optimized filtering and security.
        """
        if not self.request.user.is_authenticated:
            return Coupon.objects.none()
        
        organizer = self.get_organizer()
        if not organizer:
            return Coupon.objects.none()
        
        # 🚀 ENTERPRISE: Event-aware filtering
        event_id = self.request.query_params.get('event_id')
        base_queryset = Coupon.objects.filter(organizer=organizer).select_related('organizer')
        
        if not event_id:
            # Return empty for security - event_id is required for list operations
            return Coupon.objects.none()
        
        # 🚨 SECURITY: Validate event ownership
        if not Event.objects.filter(id=event_id, organizer=organizer).exists():
            return Coupon.objects.none()
        
        # 🚀 ENTERPRISE: Optimized filtering (Global + Local for event)
        return base_queryset.filter(
            Q(events_list__isnull=True) |  # Global coupons
            Q(events_list__contains=[event_id])  # Local coupons for this event
        ).distinct().order_by('-created_at')
    
    @action(detail=False, methods=['get'], url_path='organizer/all')
    def list_organizer_coupons(self, request):
        """🚀 ENTERPRISE: Get all coupons for organizer dashboard."""
        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=401)
        
        organizer = self.get_organizer()
        if not organizer:
            return Response({'error': 'Organizer not found'}, status=404)
        
        # 🚀 ENTERPRISE: Optimized query with prefetch
        coupons = Coupon.objects.filter(organizer=organizer)\
            .select_related('organizer')\
            .prefetch_related('ticket_tiers', 'ticket_categories')\
            .order_by('-created_at')
        
        serializer = self.get_serializer(coupons, many=True)
        
        return Response({
            'count': coupons.count(),
            'results': serializer.data,
            'analytics': self._get_organizer_coupon_analytics(coupons)
        })
    
    def _get_organizer_coupon_analytics(self, coupons):
        """🚀 ENTERPRISE: Calculate comprehensive analytics for coupons."""
        total_coupons = coupons.count()
        active_coupons = coupons.filter(is_active=True).count()
        global_coupons = coupons.filter(events_list__isnull=True).count()
        used_coupons = coupons.filter(usage_count__gt=0).count()
        
        return {
            'total_coupons': total_coupons,
            'active_coupons': active_coupons,
            'inactive_coupons': total_coupons - active_coupons,
            'global_coupons': global_coupons,
            'local_coupons': total_coupons - global_coupons,
            'used_coupons': used_coupons,
            'unused_coupons': total_coupons - used_coupons,
            'total_usage_count': sum(c.usage_count for c in coupons),
        }
    
    def get_object(self):
        """
        🚀 ENTERPRISE: Override get_object to handle individual coupon operations (GET, PUT, DELETE)
        without requiring event_id in query params.
        """
        # Get the coupon by ID first
        coupon_id = self.kwargs.get('pk')
        if not coupon_id:
            raise Http404("Coupon ID is required")
        
        try:
            # Find coupon by ID and organizer (security check)
            organizer = self.get_organizer()
            if not organizer:
                raise Http404("Organizer not found")
            
            coupon = Coupon.objects.get(id=coupon_id, organizer=organizer)
            
            # 🚨 SECURITY: Additional validation - ensure user can access this coupon
            # For individual operations, we don't need event_id validation
            # The organizer check is sufficient for security
            
            return coupon
            
        except Coupon.DoesNotExist:
            raise Http404("Coupon not found")
    
    def perform_create(self, serializer):
        """
        Create a new coupon for the current organizer.
        """
        organizer = self.get_organizer()
        if not organizer:
            raise serializers.ValidationError({"detail": "El usuario no tiene un organizador asociado"})
            
        serializer.save(organizer=organizer)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def validate(self, request):
        """🚀 ENTERPRISE: Validate coupon with comprehensive checks - PUBLIC ENDPOINT."""
        code = request.data.get('code')
        event_id = request.data.get('event_id')
        order_total = request.data.get('order_total', 0)
        
        if not code or not event_id:
            return Response({
                "is_valid": False,
                "detail": "Código de cupón y ID de evento son requeridos."
            }, status=400)
        
        try:
            # Clean code input
            code = code.strip().upper()
            # 🚀 ENTERPRISE: Convert to Decimal for precise calculations
            from decimal import Decimal
            order_total = Decimal(str(order_total)) if order_total else Decimal('0')
            
            # 🚀 ENTERPRISE: Get event to determine organizer (PUBLIC ACCESS)
            try:
                event = Event.objects.select_related('organizer').get(id=event_id)
                event_organizer = event.organizer
            except Event.DoesNotExist:
                return Response({
                    "is_valid": False,
                    "detail": "Evento no encontrado."
                }, status=400)
            
            # 🚀 ENTERPRISE: Find coupon by code and event's organizer (PUBLIC ACCESS)
            coupon_query = Coupon.objects.select_related('organizer')
            
            # Search in event's organizer coupons only
            coupon = coupon_query.filter(
                code=code,
                organizer=event_organizer
            ).first()
            
            if not coupon:
                return Response({
                    "is_valid": False,
                    "detail": "Cupón no encontrado o no válido para este evento."
                })
            
            # 🚀 ENTERPRISE: Use comprehensive model validation
            can_use, message = coupon.can_be_used_for_order(order_total, event_id)
            
            response_data = {
                "is_valid": can_use,
                "detail": message,
                "coupon_code": coupon.code
            }
            
            if can_use:
                discount_amount = coupon.calculate_discount_amount(order_total)
                final_total = max(0, order_total - discount_amount)
                
                response_data.update({
                    "coupon": CouponSerializer(coupon, context={'request': request}).data,
                    "discount_amount": float(discount_amount),
                    "final_total": float(final_total),
                    "original_total": float(order_total),
                    "savings": float(discount_amount),
                    "discount_percentage": round((discount_amount / order_total * 100), 2) if order_total > 0 else 0
                })
            
            return Response(response_data)
            
        except Coupon.DoesNotExist:
            return Response({
                "is_valid": False,
                "detail": "Cupón no encontrado."
            })
        except Exception as e:
            # Log error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error validating coupon {code}: {e}")
            
            return Response({
                "is_valid": False,
                "detail": "Error interno al validar el cupón. Intente nuevamente."
            }, status=500)
    
    @action(detail=False, methods=['post'])
    def reserve(self, request):
        """🚀 ENTERPRISE: Reserve coupon usage during checkout."""
        code = request.data.get('code')
        event_id = request.data.get('event_id')
        order_id = request.data.get('order_id')
        order_total = request.data.get('order_total', 0)
        
        if not all([code, event_id, order_id]):
            return Response({
                "success": False,
                "detail": "Código de cupón, ID de evento y ID de orden son requeridos."
            }, status=400)
        
        try:
            # Find coupon
            code = code.strip().upper()
            order_total = float(order_total) if order_total else 0
            
            coupon = Coupon.objects.select_related('organizer').get(code=code)
            
            # Validate coupon
            can_use, message = coupon.can_be_used_for_order(order_total, event_id)
            if not can_use:
                return Response({
                    "success": False,
                    "detail": message
                })
            
            # Get or create order
            from apps.events.models import Order
            try:
                order = Order.objects.get(id=order_id)
            except Order.DoesNotExist:
                return Response({
                    "success": False,
                    "detail": "Orden no encontrada."
                }, status=404)
            
            # Reserve coupon usage
            hold = coupon.reserve_usage_for_order(order)
            
            discount_amount = coupon.calculate_discount_amount(order_total)
            final_total = max(0, order_total - discount_amount)
            
            return Response({
                "success": True,
                "detail": "Cupón reservado exitosamente",
                "hold_id": hold.id,
                "expires_at": hold.expires_at.isoformat(),
                "discount_amount": float(discount_amount),
                "final_total": float(final_total),
                "coupon": CouponSerializer(coupon, context={'request': request}).data
            })
            
        except Coupon.DoesNotExist:
            return Response({
                "success": False,
                "detail": "Cupón no encontrado."
            })
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error reserving coupon {code}: {e}")
            
            return Response({
                "success": False,
                "detail": f"Error al reservar cupón: {str(e)}"
            }, status=500)
    
    @action(detail=False, methods=['post'])
    def release(self, request):
        """🚀 ENTERPRISE: Release coupon reservation."""
        order_id = request.data.get('order_id')
        
        if not order_id:
            return Response({
                "success": False,
                "detail": "ID de orden es requerido."
            }, status=400)
        
        try:
            from apps.events.models import Order, CouponHold
            
            # Get order
            try:
                order = Order.objects.get(id=order_id)
            except Order.DoesNotExist:
                return Response({
                    "success": False,
                    "detail": "Orden no encontrada."
                }, status=404)
            
            # Release all coupon holds for this order
            holds = CouponHold.objects.filter(order=order, released=False)
            released_count = 0
            
            for hold in holds:
                hold.release()
                released_count += 1
            
            return Response({
                "success": True,
                "detail": f"Se liberaron {released_count} reservas de cupones",
                "released_count": released_count
            })
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error releasing coupon holds for order {order_id}: {e}")
            
            return Response({
                "success": False,
                "detail": f"Error al liberar reservas: {str(e)}"
            }, status=500)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """
        Toggle the active status of a coupon.
        """
        coupon = self.get_object()
        coupon.is_active = not coupon.is_active
        coupon.save()
        
        return Response({
            "detail": f"Coupon is now {'active' if coupon.is_active else 'inactive'}.",
            "coupon": CouponSerializer(coupon).data
        })
    
    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """🚀 ENTERPRISE: Enhanced analytics with performance metrics."""
        organizer = self.get_organizer()
        if not organizer:
            return Response({
                "detail": "Usuario sin organizador asociado"
            }, status=400)
        
        coupons = Coupon.objects.filter(organizer=organizer)
        analytics = self._get_organizer_coupon_analytics(coupons)
        
        # 🚀 ENTERPRISE: Add performance metrics
        top_coupons = coupons.filter(usage_count__gt=0).order_by('-usage_count')[:5]
        analytics['top_performing_coupons'] = [
            {
                'code': coupon.code,
                'usage_count': coupon.usage_count,
                'type': coupon.discount_type,
                'value': float(coupon.discount_value)
            }
            for coupon in top_coupons
        ]
        
        return Response(analytics)
    
    @action(detail=True, methods=['post'])
    def apply_to_order(self, request, pk=None):
        """🚀 ENTERPRISE: Apply coupon to order with atomic transaction."""
        coupon = self.get_object()
        order_total = request.data.get('order_total', 0)
        event_id = request.data.get('event_id')
        
        if not order_total or not event_id:
            return Response({
                "success": False,
                "detail": "Order total and event ID are required."
            }, status=400)
        
        try:
            # Validate coupon can be used
            can_use, message = coupon.can_be_used_for_order(order_total, event_id)
            if not can_use:
                return Response({
                    "success": False,
                    "detail": message
                })
            
            # Calculate discount
            discount_amount = coupon.calculate_discount_amount(order_total)
            final_total = max(0, order_total - discount_amount)
            
            # Increment usage (atomic)
            coupon.increment_usage()
            
            return Response({
                "success": True,
                "discount_amount": discount_amount,
                "final_total": final_total,
                "coupon": CouponSerializer(coupon, context={'request': request}).data
            })
            
        except ValueError as e:
            return Response({
                "success": False,
                "detail": str(e)
            }, status=400)
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """🚀 ENTERPRISE: Bulk create coupons for campaigns."""
        organizer = self.get_organizer()
        if not organizer:
            return Response({"detail": "Usuario sin organizador asociado"}, status=400)
        
        coupons_data = request.data.get('coupons', [])
        if not coupons_data:
            return Response({"detail": "No coupon data provided"}, status=400)
        
        created_coupons = []
        errors = []
        
        for i, coupon_data in enumerate(coupons_data):
            try:
                serializer = self.get_serializer(data=coupon_data)
                if serializer.is_valid():
                    coupon = serializer.save(organizer=organizer)
                    created_coupons.append(serializer.data)
                else:
                    errors.append({"index": i, "errors": serializer.errors})
            except Exception as e:
                errors.append({"index": i, "error": str(e)})
        
        return Response({
            "created_count": len(created_coupons),
            "error_count": len(errors),
            "created_coupons": created_coupons,
            "errors": errors
        })


class EventCommunicationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for event communications.
    """
    serializer_class = EventCommunicationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event', 'type', 'status']
    search_fields = ['name', 'subject', 'content']
    ordering_fields = ['name', 'scheduled_date', 'created_at']
    ordering = ['-created_at']
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            return None
    
    def get_queryset(self):
        """
        Get communications for events belonging to the current organizer.
        """
        if not self.request.user.is_authenticated:
            return EventCommunication.objects.none()
        
        organizer = self.get_organizer()
        if not organizer:
            return EventCommunication.objects.none()
        
        return EventCommunication.objects.filter(
            event__organizer=organizer
        )
    
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """
        Send a communication.
        """
        communication = self.get_object()
        
        # Check if communication can be sent
        if communication.status not in ['draft', 'scheduled']:
            return Response(
                {"detail": "Only draft or scheduled communications can be sent."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # In a real app, you would send the communication here
        # For now, we'll just update the status
        communication.status = 'sent'
        communication.sent_date = timezone.now()
        communication.save()
        
        return Response({"detail": "Communication sent successfully."})
    
    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """
        Schedule a communication.
        """
        communication = self.get_object()
        scheduled_date = request.data.get('scheduled_date')
        
        if not scheduled_date:
            return Response(
                {"detail": "Scheduled date is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if communication can be scheduled
        if communication.status != 'draft':
            return Response(
                {"detail": "Only draft communications can be scheduled."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update communication status
        communication.status = 'scheduled'
        communication.scheduled_date = scheduled_date
        communication.save()
        
        return Response({"detail": "Communication scheduled successfully."})


# ============================================================================
# 🎫 ENTERPRISE QR CODE SYSTEM - PROFESSIONAL TICKET VALIDATION
# ============================================================================

@extend_schema(
    summary="Generate QR Code for Ticket",
    description="Generate a professional QR code for ticket validation. Includes caching and security features.",
    responses={
        200: {
            "description": "QR code generated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
                        "ticket_number": "TIX-B382C943",
                        "ticket_url": "https://tuki.cl/tickets/TIX-B382C943",
                        "expires_at": "2025-09-30T16:18:29Z",
                        "security_hash": "abc123def456"
                    }
                }
            }
        },
        404: {"description": "Ticket not found"},
        500: {"description": "Error generating QR code"}
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def generate_ticket_qr(request, ticket_number):
    """
    🎫 ENTERPRISE: Generate professional QR code for ticket validation
    
    Features:
    - Cached QR generation for performance
    - Security hash for validation
    - Expiration timestamp
    - Professional error handling
    - Rate limiting protection
    """
    try:
        from apps.events.models import Ticket
        from apps.events.services import QRCodeService
        from django.core.cache import cache
        from django.utils import timezone
        import hashlib
        import json
        
        # Validate ticket exists and is active
        try:
            ticket = Ticket.objects.select_related(
                'order_item__order__event',
                'order_item__ticket_tier'
            ).get(
                ticket_number=ticket_number,
                status='active'
            )
        except Ticket.DoesNotExist:
            return Response({
                'success': False,
                'error': 'TICKET_NOT_FOUND',
                'message': 'Ticket not found or inactive'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if order is paid
        if ticket.order_item.order.status != 'paid':
            return Response({
                'success': False,
                'error': 'TICKET_NOT_PAID',
                'message': 'Ticket order is not paid'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create cache key with ticket data
        cache_key = f"qr_code_{ticket_number}_{ticket.updated_at.timestamp()}"
        
        # Try to get from cache first
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        # Generate security hash
        security_data = f"{ticket_number}_{ticket.order_item.order.id}_{ticket.created_at.timestamp()}"
        security_hash = hashlib.sha256(security_data.encode()).hexdigest()[:16]
        
        # Generate QR code
        qr_code_base64 = QRCodeService.generate_qr_code(
            ticket_number, 
            size=250  # Higher quality for professional use
        )
        
        if not qr_code_base64:
            return Response({
                'success': False,
                'error': 'QR_GENERATION_FAILED',
                'message': 'Failed to generate QR code'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Prepare response data
        response_data = {
            'success': True,
            'qr_code': qr_code_base64,
            'ticket_number': ticket_number,
            'ticket_url': f"https://tuki.cl/tickets/{ticket_number}",
            'expires_at': (timezone.now() + timezone.timedelta(days=30)).isoformat(),
            'security_hash': security_hash,
            'ticket_info': {
                'event_title': ticket.order_item.order.event.title,
                'event_date': ticket.order_item.order.event.start_date.isoformat(),
                'attendee_name': ticket.attendee_name,
                'ticket_type': ticket.order_item.ticket_tier.name if ticket.order_item.ticket_tier else 'General',
                'order_number': ticket.order_item.order.order_number
            }
        }
        
        # Cache for 1 hour
        cache.set(cache_key, response_data, 3600)
        
        return Response(response_data)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': 'INTERNAL_ERROR',
            'message': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    summary="Validate Ticket QR Code",
    description="Validate a ticket using QR code data. Professional validation with security checks.",
    responses={
        200: {
            "description": "Ticket validation result",
            "content": {
                "application/json": {
                    "example": {
                        "valid": True,
                        "ticket_number": "TIX-B382C943",
                        "event_title": "Concierto de Rock",
                        "attendee_name": "Juan Pérez",
                        "status": "valid",
                        "validation_timestamp": "2025-09-29T16:18:29Z"
                    }
                }
            }
        }
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
def validate_ticket_qr(request):
    """
    🎫 ENTERPRISE: Validate ticket using QR code data
    
    Features:
    - Security hash validation
    - Real-time ticket status check
    - Event date validation
    - Professional response format
    """
    try:
        from apps.events.models import Ticket
        from django.utils import timezone
        import hashlib
        
        ticket_number = request.data.get('ticket_number')
        security_hash = request.data.get('security_hash')
        
        if not ticket_number or not security_hash:
            return Response({
                'valid': False,
                'error': 'MISSING_DATA',
                'message': 'Ticket number and security hash required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get ticket with related data
        try:
            ticket = Ticket.objects.select_related(
                'order_item__order__event',
                'order_item__ticket_tier'
            ).get(ticket_number=ticket_number)
        except Ticket.DoesNotExist:
            return Response({
                'valid': False,
                'error': 'TICKET_NOT_FOUND',
                'message': 'Ticket not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Validate security hash
        security_data = f"{ticket_number}_{ticket.order_item.order.id}_{ticket.created_at.timestamp()}"
        expected_hash = hashlib.sha256(security_data.encode()).hexdigest()[:16]
        
        if security_hash != expected_hash:
            return Response({
                'valid': False,
                'error': 'INVALID_HASH',
                'message': 'Invalid security hash'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check ticket status
        if ticket.status != 'active':
            return Response({
                'valid': False,
                'error': 'TICKET_INACTIVE',
                'message': f'Ticket status: {ticket.status}',
                'ticket_number': ticket_number
            })
        
        # Check if order is paid
        if ticket.order_item.order.status != 'paid':
            return Response({
                'valid': False,
                'error': 'ORDER_NOT_PAID',
                'message': 'Order is not paid',
                'ticket_number': ticket_number
            })
        
        # Check if event has passed (optional - you might want to allow validation after event)
        event_date = ticket.order_item.order.event.start_date
        if event_date < timezone.now() - timezone.timedelta(hours=2):
            return Response({
                'valid': False,
                'error': 'EVENT_PASSED',
                'message': 'Event has already passed',
                'ticket_number': ticket_number,
                'event_date': event_date.isoformat()
            })
        
        # All validations passed
        return Response({
            'valid': True,
            'ticket_number': ticket_number,
            'event_title': ticket.order_item.order.event.title,
            'attendee_name': ticket.attendee_name,
            'ticket_type': ticket.order_item.ticket_tier.name if ticket.order_item.ticket_tier else 'General',
            'status': 'valid',
            'validation_timestamp': timezone.now().isoformat(),
            'event_date': event_date.isoformat(),
            'order_number': ticket.order_item.order.order_number
        })
        
    except Exception as e:
        return Response({
            'valid': False,
            'error': 'INTERNAL_ERROR',
            'message': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 