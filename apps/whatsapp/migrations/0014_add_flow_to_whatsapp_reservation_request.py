# 🚀 ENTERPRISE: Platform flow on WhatsAppReservationRequest for full audit trail

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_add_platform_flow_monitoring"),
        ("whatsapp", "0013_accommodation_whatsapp_support"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappreservationrequest",
            name="flow",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_reservation_requests",
                to="core.platformflow",
                verbose_name="Platform Flow",
                help_text="Platform flow tracking this WhatsApp reservation (all steps from request to payment)",
            ),
        ),
    ]
