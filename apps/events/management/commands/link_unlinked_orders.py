"""
Management command to link existing orders to users based on email.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.events.models import Order

User = get_user_model()


class Command(BaseCommand):
    help = 'Link existing orders to users based on email address'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be linked without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write('🔗 Starting order linking process...')
        
        # Find all orders that don't have a user linked
        unlinked_orders = Order.objects.filter(user__isnull=True)
        total_unlinked = unlinked_orders.count()
        
        self.stdout.write(f'📊 Found {total_unlinked} unlinked orders')
        
        if total_unlinked == 0:
            self.stdout.write(self.style.SUCCESS('✅ All orders are already linked to users'))
            return
        
        linked_count = 0
        guest_created_count = 0
        
        for order in unlinked_orders:
            try:
                # Try to find existing user with the same email
                existing_user = User.objects.get(email__iexact=order.email)
                
                if not dry_run:
                    order.user = existing_user
                    order.save(update_fields=['user'])
                
                linked_count += 1
                self.stdout.write(f'🔗 Linked order {order.order_number} to existing user {existing_user.email}')
                
            except User.DoesNotExist:
                # Create guest user for this order
                if not dry_run:
                    guest_user = User.create_guest_user(
                        email=order.email,
                        first_name=order.first_name,
                        last_name=order.last_name
                    )
                    order.user = guest_user
                    order.save(update_fields=['user'])
                    guest_created_count += 1
                    self.stdout.write(f'👤 Created guest user and linked order {order.order_number} to {guest_user.email}')
                else:
                    guest_created_count += 1
                    self.stdout.write(f'👤 [DRY RUN] Would create guest user for order {order.order_number} ({order.email})')
            
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error processing order {order.order_number}: {str(e)}')
                )
        
        # Summary
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN SUMMARY:'))
            self.stdout.write(f'  - {linked_count} orders would be linked to existing users')
            self.stdout.write(f'  - {guest_created_count} guest users would be created')
            self.stdout.write('  - Run without --dry-run to apply changes')
        else:
            self.stdout.write(self.style.SUCCESS('✅ LINKING COMPLETE:'))
            self.stdout.write(f'  - {linked_count} orders linked to existing users')
            self.stdout.write(f'  - {guest_created_count} guest users created')
            self.stdout.write(f'  - {linked_count + guest_created_count} total orders processed')
