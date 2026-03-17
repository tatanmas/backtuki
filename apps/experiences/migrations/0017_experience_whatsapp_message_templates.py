# Optional per-experience override for WhatsApp reservation message templates

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('experiences', '0016_add_notify_whatsapp_group_on_booking'),
    ]

    operations = [
        migrations.AddField(
            model_name='experience',
            name='whatsapp_message_templates',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Optional overrides for reservation flow messages. Keys: reservation_request, customer_waiting, etc. Empty = use platform/operator default.',
                verbose_name='WhatsApp message templates',
            ),
        ),
    ]
