# Generated migration: min_nights for RentalHub, Hotel, Accommodation (hierarchical rule for booking)

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0012_alter_hotel_created_at_alter_hotel_updated_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentalhub",
            name="min_nights",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Minimum number of nights for a booking at this hub. Units inherit if they have no own rule.",
                null=True,
                verbose_name="minimum nights",
            ),
        ),
        migrations.AddField(
            model_name="hotel",
            name="min_nights",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Minimum number of nights for a booking. Rooms inherit if they have no own rule.",
                null=True,
                verbose_name="minimum nights",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="min_nights",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Minimum number of nights for a booking. Overrides hub/hotel rule when set.",
                null=True,
                validators=[MinValueValidator(1)],
                verbose_name="minimum nights",
            ),
        ),
    ]
