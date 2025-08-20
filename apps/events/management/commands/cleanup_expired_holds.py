"""
🚀 ENTERPRISE COMMAND: Clean up expired ticket holds to prevent stock leakage.

This command should be run periodically (every 5-10 minutes) via cron or Celery
to ensure that expired holds are released and tickets become available again.

Usage:
    python manage.py cleanup_expired_holds
    python manage.py cleanup_expired_holds --dry-run  # Preview what would be cleaned
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.events.models import TicketHold


class Command(BaseCommand):
    help = '🚀 ENTERPRISE: Clean up expired ticket holds to prevent stock leakage'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without actually doing it',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        dry_run = options['dry_run']
        
        # Find all expired holds that haven't been released
        expired_holds = TicketHold.objects.filter(
            released=False,
            expires_at__lte=now
        ).select_related('ticket_tier', 'event', 'order')
        
        total_holds = expired_holds.count()
        
        if total_holds == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ No expired holds found. System is clean!')
            )
            return
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'🔍 DRY RUN: Found {total_holds} expired holds that would be released:')
            )
            
            for hold in expired_holds[:10]:  # Show first 10
                self.stdout.write(
                    f'  - Hold {hold.id}: {hold.quantity}x {hold.ticket_tier.name} '
                    f'(expired {hold.expires_at}, order {hold.order_id})'
                )
            
            if total_holds > 10:
                self.stdout.write(f'  ... and {total_holds - 10} more')
                
            return
        
        # Actually release the holds
        self.stdout.write(f'🧹 Cleaning up {total_holds} expired holds...')
        
        released_count = 0
        tickets_returned = 0
        
        for hold in expired_holds:
            try:
                hold.release()  # This returns tickets to availability
                released_count += 1
                tickets_returned += hold.quantity
                
                if released_count % 100 == 0:  # Progress indicator for large batches
                    self.stdout.write(f'  Processed {released_count}/{total_holds} holds...')
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error releasing hold {hold.id}: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Successfully released {released_count} expired holds, '
                f'returning {tickets_returned} tickets to availability!'
            )
        )
        
        if released_count != total_holds:
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  {total_holds - released_count} holds could not be released. '
                    'Check logs for errors.'
                )
            )

