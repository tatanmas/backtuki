"""
🚀 ENTERPRISE: Ticket management views
Advanced ticket operations including holds, reservations, and analytics
"""

from django.utils import timezone
from django.db.models import Sum, Count, Q
from decimal import Decimal
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from apps.events.models import TicketTier, TicketHold, Order, OrderItem
from api.v1.events.serializers import TicketTierSerializer


class TicketTierManagementViewSet(viewsets.ModelViewSet):
    """
    🚀 ENTERPRISE: Advanced ticket tier management
    Provides detailed analytics, hold management, and revenue calculations
    """
    serializer_class = TicketTierSerializer
    permission_classes = [permissions.IsAuthenticated]  # Usar el mismo patrón que endpoints que funcionan
    
    def get_queryset(self):
        """Filter queryset by organizer like TicketTierViewSet"""
        organizer = self.get_organizer()
        if not organizer:
            return TicketTier.objects.none()
        return TicketTier.objects.filter(event__organizer=organizer)
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual (mismo patrón que TicketTierViewSet)."""
        if hasattr(self.request.user, 'get_primary_organizer'):
            return self.request.user.get_primary_organizer()
        return None

    @action(detail=True, methods=['get'])
    def holds(self, request, pk=None):
        """
        🚀 ENTERPRISE: Get detailed hold information for a ticket tier
        Returns active holds, reserved quantities, and expiration details
        """
        try:
            ticket_tier = TicketTier.objects.get(id=pk)
            
            # Permission check usando el mismo patrón que TicketTierViewSet
            organizer = self.get_organizer()
            if not organizer:
                return Response({"detail": "No organizer found for user"}, status=status.HTTP_403_FORBIDDEN)
            
            if ticket_tier.event.organizer != organizer:
                return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
            
            now = timezone.now()
            
            # Get active holds (not expired, not released)
            active_holds = TicketHold.objects.filter(
                ticket_tier=ticket_tier,
                released=False,
                expires_at__gt=now
            )
            
            # Calculate totals
            total_on_hold = active_holds.aggregate(total=Sum('quantity'))['total'] or 0
            
            # Group by expiration time for detailed view
            holds_by_expiration = {}
            for hold in active_holds:
                exp_key = hold.expires_at.isoformat()
                if exp_key not in holds_by_expiration:
                    holds_by_expiration[exp_key] = {
                        'expires_at': hold.expires_at.isoformat(),
                        'quantity': 0,
                        'orders': []
                    }
                holds_by_expiration[exp_key]['quantity'] += hold.quantity
                if hold.order:
                    holds_by_expiration[exp_key]['orders'].append({
                        'order_id': str(hold.order.id),
                        'order_number': hold.order.order_number,
                        'email': hold.order.email
                    })
            
            return Response({
                'ticket_tier_id': str(ticket_tier.id),
                'active_holds': total_on_hold,
                'total_reserved': total_on_hold,  # For compatibility
                'holds_detail': list(holds_by_expiration.values()),
                'capacity': ticket_tier.capacity,
                'available': ticket_tier.available,
                'sold': ticket_tier.tickets_sold,  # 🚀 ENTERPRISE: Use real sold data
                'real_available': max(0, ticket_tier.available - total_on_hold),
                'last_updated': now.isoformat()
            })
            
        except TicketTier.DoesNotExist:
            return Response({"detail": "Ticket tier not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def revenue(self, request, pk=None):
        """
        🚀 ENTERPRISE: Calculate accurate revenue for a ticket tier
        Uses centralized revenue calculator for consistency
        """
        try:
            ticket_tier = TicketTier.objects.get(id=pk)
            
            # Check permissions using the same pattern as other methods
            organizer = self.get_organizer()
            if not organizer or ticket_tier.event.organizer != organizer:
                return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
            
            # 🚀 ENTERPRISE: Use centralized revenue calculator
            from core.revenue_calculator import calculate_ticket_tier_revenue
            
            # Get optional date filters
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            from django.utils.dateparse import parse_datetime
            start_date_parsed = parse_datetime(start_date) if start_date else None
            end_date_parsed = parse_datetime(end_date) if end_date else None
            
            # Calculate revenue using centralized function
            revenue_result = calculate_ticket_tier_revenue(
                ticket_tier,
                start_date=start_date_parsed,
                end_date=end_date_parsed,
                validate=True
            )
            
            # Extract values
            total_revenue = revenue_result['total_revenue']
            total_service_fees = revenue_result['service_fees']
            total_net_revenue = revenue_result['gross_revenue']
            orders_count = revenue_result['total_orders']
            tickets_sold = revenue_result['total_tickets']
            
            # For pricing history, we still need to look at individual order items to see price variations
            paid_order_items = OrderItem.objects.filter(
                ticket_tier=ticket_tier,
                order__status='paid'
            ).select_related('order')
            
            revenue_by_price = {}  # Track different price points
            
            for item in paid_order_items:
                # For pricing history, use the proportion of the order that corresponds to this item
                # This handles PWYW correctly by using the actual order totals
                order = item.order
                order_total_items = order.items.aggregate(total_qty=Sum('quantity'))['total_qty'] or 1
                
                # Calculate this item's share of the order total (using Decimal for precision)
                item_share = Decimal(item.quantity) / Decimal(order_total_items)
                item_order_subtotal = float(order.subtotal * item_share)
                item_order_service_fee = float(order.service_fee * item_share)
                item_order_total = float(order.total * item_share)
                
                # Use the calculated per-unit prices for grouping
                unit_subtotal = item_order_subtotal / item.quantity if item.quantity > 0 else 0
                unit_service_fee = item_order_service_fee / item.quantity if item.quantity > 0 else 0
                unit_total = item_order_total / item.quantity if item.quantity > 0 else 0
                
                price_key = f"{unit_subtotal:.2f}_{unit_service_fee:.2f}"
                if price_key not in revenue_by_price:
                    revenue_by_price[price_key] = {
                        'base_price': unit_subtotal,
                        'service_fee': unit_service_fee,
                        'total_price': unit_total,
                        'tickets_sold': 0,
                        'revenue': 0
                    }
                revenue_by_price[price_key]['tickets_sold'] += item.quantity
                revenue_by_price[price_key]['revenue'] += item_order_total
            
            # Current pricing info
            current_base_price = float(ticket_tier.price)
            current_service_fee = float(ticket_tier.service_fee)
            current_total_price = current_base_price + current_service_fee
            
            return Response({
                'ticket_tier_id': str(ticket_tier.id),
                'name': ticket_tier.name,
                'current_pricing': {
                    'base_price': current_base_price,
                    'service_fee': current_service_fee,
                    'total_price': current_total_price
                },
                'sales_summary': {
                    'tickets_sold': tickets_sold,
                    'orders_count': orders_count,
                    'total_revenue': float(total_revenue),  # Total paid by customers
                    'total_service_fees': float(total_service_fees),  # Platform commission
                    'net_revenue': float(total_net_revenue),  # Organizer income
                },
                'pricing_history': list(revenue_by_price.values()),
                'capacity_info': {
                    'total_capacity': ticket_tier.capacity,
                    'available': ticket_tier.available,
                    'sold': tickets_sold,
                    'utilization_rate': (tickets_sold / ticket_tier.capacity * 100) if ticket_tier.capacity and ticket_tier.capacity > 0 else 0
                },
                'last_updated': timezone.now().isoformat()
            })
            
        except TicketTier.DoesNotExist:
            return Response({"detail": "Ticket tier not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def release_holds(self, request, pk=None):
        """
        🚀 ENTERPRISE: Release all expired holds for a ticket tier
        Useful for cleaning up and freeing inventory
        """
        try:
            ticket_tier = TicketTier.objects.get(id=pk)
            
            # Check permissions
            organizer = request.user.get_primary_organizer() if hasattr(request.user, 'get_primary_organizer') else None
            if not organizer or ticket_tier.event.organizer != organizer:
                return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
            
            now = timezone.now()
            
            # Find expired holds
            expired_holds = TicketHold.objects.filter(
                ticket_tier=ticket_tier,
                released=False,
                expires_at__lte=now
            )
            
            released_count = 0
            freed_tickets = 0
            
            for hold in expired_holds:
                freed_tickets += hold.quantity
                hold.release()  # This updates tier.available
                released_count += 1
            
            return Response({
                'ticket_tier_id': str(ticket_tier.id),
                'released_holds': released_count,
                'freed_tickets': freed_tickets,
                'new_available': ticket_tier.available,
                'message': f'Released {released_count} expired holds, freeing {freed_tickets} tickets'
            })
            
        except TicketTier.DoesNotExist:
            return Response({"detail": "Ticket tier not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """
        🚀 ENTERPRISE: Get real-time availability including holds
        Returns comprehensive availability data for transparent inventory management
        """
        try:
            ticket_tier = TicketTier.objects.get(id=pk)
            
            # Permission check usando el mismo patrón que TicketTierViewSet
            organizer = self.get_organizer()
            if not organizer:
                return Response({"detail": "No organizer found for user"}, status=status.HTTP_403_FORBIDDEN)
            
            if ticket_tier.event.organizer != organizer:
                return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
            
            # Get comprehensive availability summary
            availability = ticket_tier.get_availability_summary()
            
            # 🚀 DEBUG: Log availability data
            print(f"🔍 AVAILABILITY DEBUG - Ticket Tier: {ticket_tier.name}")
            print(f"🔍 AVAILABILITY DEBUG - Raw availability: {availability}")
            print(f"🔍 AVAILABILITY DEBUG - tickets_on_hold property: {ticket_tier.tickets_on_hold}")
            print(f"🔍 AVAILABILITY DEBUG - Total holds in DB: {ticket_tier.holds.count()}")
            print(f"🔍 AVAILABILITY DEBUG - Active holds: {ticket_tier.holds.filter(released=False).count()}")
            
            return Response({
                'ticket_tier_id': str(ticket_tier.id),
                'name': ticket_tier.name,
                'availability': availability,
                'pricing': {
                    'base_price': float(ticket_tier.price),
                    'service_fee': float(ticket_tier.service_fee),
                    'total_price': float(ticket_tier.price + ticket_tier.service_fee)
                },
                'limits': {
                    'min_per_order': ticket_tier.min_per_order,
                    'max_per_order': ticket_tier.max_per_order
                },
                'status': {
                    'is_public': ticket_tier.is_public,
                    'is_sold_out': ticket_tier.is_sold_out,
                    'can_purchase': ticket_tier.real_available > 0
                },
                'last_updated': timezone.now().isoformat()
            })
            
        except TicketTier.DoesNotExist:
            return Response({"detail": "Ticket tier not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
