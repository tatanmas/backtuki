"""
🚀 ENTERPRISE: Ticket management views
Advanced ticket operations including holds, reservations, and analytics
"""

from django.utils import timezone
from django.db.models import Sum, Count, Q
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from apps.events.models import TicketTier, TicketHold, Order, OrderItem
from apps.organizers.models import OrganizerUser
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
        try:
            organizer_user = OrganizerUser.objects.get(user=self.request.user)
            return organizer_user.organizer
        except OrganizerUser.DoesNotExist:
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
        Returns revenue based on actual orders, not tier price × sold tickets
        """
        try:
            ticket_tier = TicketTier.objects.get(id=pk)
            
            # Check permissions
            if not hasattr(request.user, 'organizer') or ticket_tier.event.organizer != request.user.organizer:
                return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
            
            # Get all paid orders for this ticket tier
            paid_order_items = OrderItem.objects.filter(
                ticket_tier=ticket_tier,
                order__status='paid'
            ).select_related('order')
            
            # Calculate revenue from actual orders (enterprise approach)
            total_revenue = 0
            total_service_fees = 0
            total_net_revenue = 0
            orders_count = 0
            tickets_sold = 0
            
            revenue_by_price = {}  # Track different price points
            
            for item in paid_order_items:
                # Revenue calculation based on actual order amounts
                item_subtotal = item.quantity * item.price
                item_service_fee = item.quantity * item.service_fee
                item_total = item_subtotal + item_service_fee
                
                total_revenue += item_total
                total_service_fees += item_service_fee
                total_net_revenue += item_subtotal
                tickets_sold += item.quantity
                orders_count += 1
                
                # Track revenue by price point
                price_key = f"{item.price}_{item.service_fee}"
                if price_key not in revenue_by_price:
                    revenue_by_price[price_key] = {
                        'base_price': float(item.price),
                        'service_fee': float(item.service_fee),
                        'total_price': float(item.price + item.service_fee),
                        'tickets_sold': 0,
                        'revenue': 0
                    }
                revenue_by_price[price_key]['tickets_sold'] += item.quantity
                revenue_by_price[price_key]['revenue'] += item_total
            
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
            if not hasattr(request.user, 'organizer') or ticket_tier.event.organizer != request.user.organizer:
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
