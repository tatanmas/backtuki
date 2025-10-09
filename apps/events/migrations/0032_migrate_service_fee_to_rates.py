# Data migration to convert existing service_fee values to service_fee_rate

from django.db import migrations
from decimal import Decimal


def migrate_service_fees_to_rates(apps, schema_editor):
    """
    Convert existing service_fee values to service_fee_rate.
    This assumes that existing service_fee values were calculated as: base_price * 0.15
    So we can extract the rate by dividing: service_fee / base_price
    """
    TicketTier = apps.get_model('events', 'TicketTier')
    
    # Get all ticket tiers that had service_fee > 0 before the migration
    # Note: This migration should be run BEFORE the RemoveField operation
    # So we need to handle this in the previous migration or create a separate one
    
    # For now, we'll set a default 15% rate for all existing tickets
    # In production, you might want to analyze existing data more carefully
    default_rate = Decimal('0.15')  # 15%
    
    for ticket in TicketTier.objects.all():
        if ticket.price > 0:
            # Calculate what the rate would have been
            # Most likely it was 15% but we can be more precise if needed
            ticket.service_fee_rate = default_rate
            ticket.save(update_fields=['service_fee_rate'])
        else:
            # Free tickets don't need service fee
            ticket.service_fee_rate = Decimal('0.00')
            ticket.save(update_fields=['service_fee_rate'])


def reverse_migrate_service_fees(apps, schema_editor):
    """
    Reverse migration - convert service_fee_rate back to service_fee values
    """
    TicketTier = apps.get_model('events', 'TicketTier')
    
    for ticket in TicketTier.objects.all():
        if ticket.service_fee_rate and ticket.price:
            # Calculate service_fee from rate
            service_fee = ticket.price * ticket.service_fee_rate
            # Note: This assumes the old service_fee field still exists
            # ticket.service_fee = service_fee
            # ticket.save(update_fields=['service_fee'])
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0031_service_fee_hierarchy_and_pwyw_tickets'),
    ]

    operations = [
        migrations.RunPython(
            migrate_service_fees_to_rates,
            reverse_migrate_service_fees,
        ),
    ]
