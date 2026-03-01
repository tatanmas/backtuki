# Accommodation.external_id for channel manager / PMS room mapping

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0010_hotel_and_room_inheritance"),
    ]

    operations = [
        migrations.AddField(
            model_name="accommodation",
            name="external_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Optional mapping for channel manager / PMS room or rate ID.",
                max_length=255,
                verbose_name="external ID for channel manager",
            ),
        ),
    ]
