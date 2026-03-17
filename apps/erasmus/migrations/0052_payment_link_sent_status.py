# Link sent status on ErasmusActivityPaymentLink (automatic / manual / error)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erasmus', '0051_post_purchase_message_on_instance'),
    ]

    operations = [
        migrations.AddField(
            model_name='erasmusactivitypaymentlink',
            name='link_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When the payment link was sent to the lead (WhatsApp).',
                null=True,
                verbose_name='link sent at',
            ),
        ),
        migrations.AddField(
            model_name='erasmusactivitypaymentlink',
            name='link_sent_via',
            field=models.CharField(
                blank=True,
                choices=[('automatic', 'Automático'), ('manual', 'Manual')],
                help_text='Whether the link was sent automatically (flow) or marked as sent manually.',
                max_length=20,
                null=True,
                verbose_name='link sent via',
            ),
        ),
        migrations.AddField(
            model_name='erasmusactivitypaymentlink',
            name='link_send_error',
            field=models.CharField(
                blank=True,
                help_text='Error message if automatic send failed (e.g. WhatsApp disconnected).',
                max_length=255,
                null=True,
                verbose_name='link send error',
            ),
        ),
    ]
