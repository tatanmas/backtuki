# Add car_rental_ids and car_rental to featured_type choices

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("landing_destinations", "0003_alter_landingdestination_images_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="landingdestination",
            name="car_rental_ids",
            field=models.JSONField(
                default=list,
                help_text="List of car UUIDs (Car model from car_rental app) to show on destination page",
                verbose_name="car rental IDs",
            ),
        ),
        migrations.AlterField(
            model_name="landingdestination",
            name="featured_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("experience", "Experience"),
                    ("event", "Event"),
                    ("accommodation", "Accommodation"),
                    ("car_rental", "Car rental"),
                ],
                max_length=20,
                null=True,
                verbose_name="featured type",
            ),
        ),
    ]
