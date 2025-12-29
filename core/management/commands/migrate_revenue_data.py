"""
🚀 ENTERPRISE: Django management command to migrate historical revenue data.

Usage:
    python manage.py migrate_revenue_data [--batch-size 100] [--dry-run]

This command calculates and stores effective values for all existing orders
that don't have them yet.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from core.revenue_system import migrate_all_orders, migrate_order_effective_values
from apps.events.models import Order


class Command(BaseCommand):
    help = 'Migrate historical revenue data to use effective values'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of orders to process in each batch (default: 100)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate migration without making changes'
        )
        parser.add_argument(
            '--order-id',
            type=int,
            help='Migrate a specific order by ID'
        )
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Skip confirmation prompt'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        order_id = options.get('order_id')

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))

        if order_id:
            # Migrate specific order
            try:
                order = Order.objects.get(id=order_id)
                self.stdout.write(f'Migrating order {order.order_number}...')
                
                if not dry_run:
                    success = migrate_order_effective_values(order)
                    if success:
                        self.stdout.write(self.style.SUCCESS(f'✅ Successfully migrated order {order.order_number}'))
                    else:
                        self.stdout.write(self.style.ERROR(f'❌ Failed to migrate order {order.order_number}'))
                else:
                    self.stdout.write(self.style.WARNING(f'Would migrate order {order.order_number}'))
                    
            except Order.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ Order {order_id} not found'))
                return
        else:
            # Migrate all orders
            orders_to_migrate = Order.objects.filter(
                subtotal_effective__isnull=True,
                status='paid'
            )
            total_orders = orders_to_migrate.count()
            
            self.stdout.write(f'Found {total_orders} orders to migrate')
            
            if total_orders == 0:
                self.stdout.write(self.style.SUCCESS('✅ All orders already migrated!'))
                return
            
            if dry_run:
                self.stdout.write(self.style.WARNING(f'Would migrate {total_orders} orders'))
                
                # Show sample of orders that would be migrated
                sample = orders_to_migrate[:5]
                self.stdout.write('\nSample orders:')
                for order in sample:
                    self.stdout.write(f'  - {order.order_number}: subtotal={order.subtotal}, service_fee={order.service_fee}, discount={order.discount}, total={order.total}')
                
                if total_orders > 5:
                    self.stdout.write(f'  ... and {total_orders - 5} more')
            else:
                # Confirm migration
                if not options.get('yes'):
                    confirm = input(f'\n⚠️  This will migrate {total_orders} orders. Continue? (yes/no): ')
                    if confirm.lower() != 'yes':
                        self.stdout.write(self.style.WARNING('Migration cancelled'))
                        return
                
                self.stdout.write(f'\n🚀 Starting migration of {total_orders} orders...')
                
                # Run migration
                summary = migrate_all_orders(batch_size=batch_size)
                
                # Display results
                self.stdout.write('\n' + '='*60)
                self.stdout.write('MIGRATION SUMMARY')
                self.stdout.write('='*60)
                self.stdout.write(f'Total orders: {summary["total_orders"]}')
                self.stdout.write(f'Migrated: {summary["migrated"]}')
                self.stdout.write(f'Failed: {summary["failed"]}')
                self.stdout.write(f'Success rate: {summary["success_rate"]:.2f}%')
                self.stdout.write('='*60)
                
                if summary['failed'] == 0:
                    self.stdout.write(self.style.SUCCESS('\n✅ Migration completed successfully!'))
                else:
                    self.stdout.write(self.style.WARNING(f'\n⚠️  Migration completed with {summary["failed"]} failures'))
                    self.stdout.write('Check logs for details on failed orders')

