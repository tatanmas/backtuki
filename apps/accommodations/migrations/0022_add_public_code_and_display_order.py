# Generated manually: public_code (tuqui1-xxx) and display_order for accommodations.
# Code is generated automatically when publishing; not required for JSON/create.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0021_full_bathrooms_half_bathrooms"),
    ]

    operations = [
        migrations.AddField(
            model_name="accommodation",
            name="public_code",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Unique code generated when published (e.g. tuqui1-a1b2c3). Not required for JSON/create.",
                max_length=64,
                null=True,
                unique=True,
                verbose_name="public code",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="display_order",
            field=models.PositiveIntegerField(
                blank=True,
                db_index=True,
                help_text="Order number starting from 1. Assigned automatically when published if not set.",
                null=True,
                verbose_name="display order",
            ),
        ),
    ]
