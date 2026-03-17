# Migration: default WhatsApp group for Hotel and RentalHub (reservation coordination hierarchy)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accommodations', '0016_alter_accommodation_whatsapp_message_templates_and_more'),
        ('whatsapp', '0002_whatsappchat_whatsappreservationcode_and_more'),  # WhatsAppChat exists from 0002
    ]

    operations = [
        migrations.AddField(
            model_name='rentalhub',
            name='default_whatsapp_group',
            field=models.ForeignKey(
                blank=True,
                help_text='WhatsApp group for reservation coordination. Units without their own group use this.',
                limit_choices_to={'type': 'group'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rental_hub_default_for',
                to='whatsapp.whatsappchat',
                verbose_name='Default WhatsApp group',
            ),
        ),
        migrations.AddField(
            model_name='hotel',
            name='default_whatsapp_group',
            field=models.ForeignKey(
                blank=True,
                help_text='WhatsApp group for reservation coordination. Rooms without their own group use this.',
                limit_choices_to={'type': 'group'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='hotel_default_for',
                to='whatsapp.whatsappchat',
                verbose_name='Default WhatsApp group',
            ),
        ),
    ]
