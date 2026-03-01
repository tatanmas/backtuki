# Per-instance instructions (shown in details) and WhatsApp message (sent after registration)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0037_erasmusactivitypubliclink"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmusactivityinstance",
            name="instructions_es",
            field=models.TextField(blank=True, help_text="Instructions shown in activity details (Spanish).", verbose_name="instructions Spanish"),
        ),
        migrations.AddField(
            model_name="erasmusactivityinstance",
            name="instructions_en",
            field=models.TextField(blank=True, help_text="Instructions shown in activity details (English).", verbose_name="instructions English"),
        ),
        migrations.AddField(
            model_name="erasmusactivityinstance",
            name="whatsapp_message_es",
            field=models.TextField(blank=True, help_text="Message sent by WhatsApp to the lead after they register (Spanish).", verbose_name="WhatsApp message Spanish"),
        ),
        migrations.AddField(
            model_name="erasmusactivityinstance",
            name="whatsapp_message_en",
            field=models.TextField(blank=True, help_text="Message sent by WhatsApp to the lead after they register (English).", verbose_name="WhatsApp message English"),
        ),
    ]
