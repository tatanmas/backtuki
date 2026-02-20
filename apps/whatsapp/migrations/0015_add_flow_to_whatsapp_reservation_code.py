# 🚀 ENTERPRISE: Platform flow on WhatsAppReservationCode (started at code generation)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_add_platform_flow_monitoring"),
        ("whatsapp", "0014_add_flow_to_whatsapp_reservation_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappreservationcode",
            name="flow",
            field=models.ForeignKey(
                blank=True,
                help_text="Flow started at code generation; reused when WhatsApp message is received.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_reservation_codes",
                to="core.platformflow",
                verbose_name="Platform Flow",
            ),
        ),
    ]
