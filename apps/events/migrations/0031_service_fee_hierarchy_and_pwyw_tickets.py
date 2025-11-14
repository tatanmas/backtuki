# Generated manually for service fee hierarchy and Pay-What-You-Want tickets implementation

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0030_add_soft_delete_to_event'),
    ]

    operations = [
        # 1. Add service fee rate to Event model
        migrations.AddField(
            model_name='event',
            name='service_fee_rate',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Service fee rate for this event (e.g., 0.15 for 15%). If null, uses organizer\'s default.',
                max_digits=5,
                null=True,
                verbose_name='service fee rate'
            ),
        ),
        
        # 2. Remove TYPE_CHOICES constraint from TicketTier.type field
        migrations.AlterField(
            model_name='tickettier',
            name='type',
            field=models.CharField(
                blank=True,
                help_text='Free text field for ticket type (e.g., \'VIP\', \'Early Bird\', \'General\')',
                max_length=50,
                verbose_name='type'
            ),
        ),
        
        # 3. Replace service_fee with service_fee_rate in TicketTier
        migrations.RemoveField(
            model_name='tickettier',
            name='service_fee',
        ),
        migrations.AddField(
            model_name='tickettier',
            name='service_fee_rate',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Service fee rate for this ticket (e.g., 0.15 for 15%). If null, uses event or organizer default.',
                max_digits=5,
                null=True,
                verbose_name='service fee rate'
            ),
        ),
        
        # 4. Add Pay-What-You-Want fields to TicketTier
        migrations.AddField(
            model_name='tickettier',
            name='is_pay_what_you_want',
            field=models.BooleanField(
                default=False,
                help_text='If true, users can choose how much to pay for this ticket',
                verbose_name='is pay what you want'
            ),
        ),
        migrations.AddField(
            model_name='tickettier',
            name='min_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Minimum price for pay-what-you-want tickets (optional)',
                max_digits=10,
                null=True,
                verbose_name='minimum price'
            ),
        ),
        migrations.AddField(
            model_name='tickettier',
            name='max_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Maximum price for pay-what-you-want tickets (optional)',
                max_digits=10,
                null=True,
                verbose_name='maximum price'
            ),
        ),
        migrations.AddField(
            model_name='tickettier',
            name='suggested_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Suggested price to show users for pay-what-you-want tickets (optional)',
                max_digits=10,
                null=True,
                verbose_name='suggested price'
            ),
        ),
        
        # 5. Add custom_price field to OrderItem
        migrations.AddField(
            model_name='orderitem',
            name='custom_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='User-selected price for pay-what-you-want tickets',
                max_digits=10,
                null=True,
                verbose_name='custom price'
            ),
        ),
    ]
