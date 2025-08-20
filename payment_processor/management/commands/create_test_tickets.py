"""
🚀 ENTERPRISE: Create test tickets for orders
"""

from django.core.management.base import BaseCommand
from apps.events.models import Order, OrderItem, Ticket
from decimal import Decimal
import uuid
from django.db.models import Sum


class Command(BaseCommand):
    help = '🚀 Create test tickets for existing orders'

    def add_arguments(self, parser):
        parser.add_argument(
            '--order-id',
            type=str,
            help='Order ID to create tickets for'
        )

    def handle(self, *args, **options):
        self.stdout.write('🚀 Creating test tickets for orders...')
        
        try:
            order_id = options.get('order_id')
            
            if order_id:
                try:
                    order = Order.objects.get(id=order_id)
                    self.stdout.write(f'✅ Using order: {order.order_number}')
                except Order.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f'❌ Order {order_id} not found'))
                    return
            else:
                # Find a paid order
                order = Order.objects.filter(status='paid').first()
                if not order:
                    self.stdout.write(self.style.ERROR('❌ No paid orders found. Create an order and mark it as paid first.'))
                    return
                
                self.stdout.write(f'✅ Using order: {order.order_number}')
            
            # Create tickets for each order item
            for item in order.items.all():
                self.stdout.write(f'📝 Creating {item.quantity} tickets for {item.ticket_tier.name}')
                
                for i in range(item.quantity):
                    # Generate test attendee data
                    attendee_number = i + 1
                    first_name = f"Test{attendee_number}"
                    last_name = "Attendee"
                    email = f"test{attendee_number}@example.com"
                    
                    ticket = Ticket.objects.create(
                        order_item=item,
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        status='active',
                        check_in_status='pending'
                    )
                    
                    self.stdout.write(f'   ✅ Created ticket: {ticket.ticket_number} for {ticket.attendee_name}')
            
            self.stdout.write(self.style.SUCCESS(f'✅ Successfully created tickets for order {order.order_number}'))
            self.stdout.write(f'   - Total tickets created: {order.items.aggregate(total=Sum("quantity"))["total"]}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'💥 Error: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
