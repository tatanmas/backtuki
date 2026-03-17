# Post-purchase message (ES/EN) on instance for confirmation email and optional WhatsApp

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erasmus', '0050_erasmus_activity_payment_link_lead_instance_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='erasmusactivityinstance',
            name='post_purchase_message_es',
            field=models.TextField(
                blank=True,
                help_text='Message in confirmation email and optional WhatsApp after payment (Spanish). Same placeholders as WhatsApp message.',
                verbose_name='Post-purchase message Spanish',
            ),
        ),
        migrations.AddField(
            model_name='erasmusactivityinstance',
            name='post_purchase_message_en',
            field=models.TextField(
                blank=True,
                help_text='Message in confirmation email and optional WhatsApp after payment (English). Same placeholders as WhatsApp message.',
                verbose_name='Post-purchase message English',
            ),
        ),
    ]
