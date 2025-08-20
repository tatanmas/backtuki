"""
🚀 ENTERPRISE: Create test orders for payment testing
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from apps.events.models import Order, Event, TicketTier, OrderItem
from decimal import Decimal
import uuid


class Command(BaseCommand):
    help = '🚀 Create test orders for payment testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--amount',
            type=float,
            default=5000.0,
            help='Amount for the test order (default: 5000 CLP)'
        )
        parser.add_argument(
            '--event-id',
            type=str,
            help='Event ID to create order for (optional)'
        )

    def handle(self, *args, **options):
        self.stdout.write('🚀 Creating test order for payment testing...')
        
        try:
            amount = Decimal(str(options.get('amount')))
            event_id = options.get('event_id')
            
            # Get or create event
            if event_id:
                try:
                    event = Event.objects.get(id=event_id)
                    self.stdout.write(f'✅ Using existing event: {event.title}')
                except Event.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f'❌ Event {event_id} not found'))
                    return
            else:
                # Create a test event if none exists
                event = Event.objects.first()
                if not event:
                    self.stdout.write(self.style.ERROR('❌ No events found. Create an event first.'))
                    return
                
                self.stdout.write(f'✅ Using event: {event.title}')
            
            # Get or create ticket tier
            ticket_tier = event.ticket_tiers.first()
            if not ticket_tier:
                # Create a test ticket tier
                ticket_tier = TicketTier.objects.create(
                    event=event,
                    name="Test Ticket",
                    type="general",
                    price=amount,
                    capacity=100,
                    available=100,
                    is_public=True
                )
                self.stdout.write(f'✅ Created test ticket tier: {ticket_tier.name}')
            else:
                self.stdout.write(f'✅ Using ticket tier: {ticket_tier.name}')
            
            # Create test order
            order = Order.objects.create(
                event=event,
                email="test@example.com",
                first_name="Test",
                last_name="User",
                phone="+56912345678",
                subtotal=amount,
                service_fee=Decimal('0'),
                total=amount,
                currency='CLP',
                status='pending'
            )
            
            # Create order item
            order_item = OrderItem.objects.create(
                order=order,
                ticket_tier=ticket_tier,
                quantity=1,
                unit_price=amount,
                unit_service_fee=Decimal('0')
            )
            
            self.stdout.write(self.style.SUCCESS(f'✅ Created test order: {order.order_number}'))
            self.stdout.write(f'   - Order ID: {order.id}')
            self.stdout.write(f'   - Amount: ${order.total}')
            self.stdout.write(f'   - Status: {order.status}')
            self.stdout.write(f'   - Event: {event.title}')
            self.stdout.write('')
            self.stdout.write('🎯 You can now test payments with:')
            self.stdout.write(f'   python manage.py test_payment_system --order-id {order.id}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'💥 Error: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
