# WhatsApp reservation message templates (3-layer: room -> hotel/central -> platform)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accommodations', '0014_accommodation_payment_model_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalhub',
            name='whatsapp_message_templates',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Optional overrides for reservation flow messages (central level). Keys: reservation_request, customer_waiting, etc. Empty = use platform default.',
                verbose_name='WhatsApp reservation message templates',
            ),
        ),
        migrations.AddField(
            model_name='hotel',
            name='whatsapp_message_templates',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Optional overrides for reservation flow messages (hotel level). Rooms inherit; room override wins.',
                verbose_name='WhatsApp reservation message templates',
            ),
        ),
        migrations.AddField(
            model_name='accommodation',
            name='whatsapp_message_templates',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Optional overrides for reservation flow messages (room/unit level). Wins over hotel/central and platform.',
                verbose_name='WhatsApp reservation message templates',
            ),
        ),
    ]
