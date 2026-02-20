# 🚀 ENTERPRISE: Platform flow on AccommodationReservation for audit trail

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_add_platform_flow_monitoring"),
        ("accommodations", "0003_gallery_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="accommodationreservation",
            name="flow",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="accommodation_reservations",
                to="core.platformflow",
                verbose_name="platform flow",
                help_text="Platform flow tracking this reservation (for traceability)",
            ),
        ),
    ]
