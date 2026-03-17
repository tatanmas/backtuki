# Free tour: notify WhatsApp group on each new booking

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('experiences', '0015_add_experience_imported_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='experience',
            name='notify_whatsapp_group_on_booking',
            field=models.BooleanField(
                default=False,
                help_text='If True and a WhatsApp group is linked, send a message to the group for each new free tour booking',
                verbose_name='notify WhatsApp group on booking'
            ),
        ),
    ]
