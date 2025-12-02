# Generated manually for raffle support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0038_add_flow_to_order'),
    ]

    operations = [
        # 1. Add 'rifa' to Event.TYPE_CHOICES
        migrations.AlterField(
            model_name='event',
            name='type',
            field=models.CharField(
                choices=[
                    ('conference', 'Conference'),
                    ('concert', 'Concert'),
                    ('sports', 'Sports'),
                    ('theater', 'Theater'),
                    ('workshop', 'Workshop'),
                    ('festival', 'Festival'),
                    ('party', 'Party'),
                    ('rifa', 'Rifa'),
                    ('other', 'Other'),
                ],
                default='other',
                max_length=20,
                verbose_name='type'
            ),
        ),
        
        # 2. Add is_raffle field to TicketTier
        migrations.AddField(
            model_name='tickettier',
            name='is_raffle',
            field=models.BooleanField(
                default=False,
                help_text='If true, this ticket is a raffle entry (no QR code generation)',
                verbose_name='is raffle'
            ),
        ),
    ]

