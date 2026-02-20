# Add form_locale: language the lead used to view the registration form (for welcome WhatsApp message)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0025_add_erasmus_whatsapp_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmuslead",
            name="form_locale",
            field=models.CharField(
                blank=True,
                default="es",
                help_text="Language the lead used to view the registration form (es, en, pt, de, it, fr). Used for welcome WhatsApp message.",
                max_length=10,
                verbose_name="form locale",
            ),
        ),
    ]
