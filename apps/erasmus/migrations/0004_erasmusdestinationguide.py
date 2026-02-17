# Generated migration: ErasmusDestinationGuide

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0003_add_stay_reason"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErasmusDestinationGuide",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "destination_slug",
                    models.CharField(
                        db_index=True,
                        help_text="Slug del destino (ej. san-pedro-atacama, torres-del-paine)",
                        max_length=120,
                        verbose_name="destination slug",
                    ),
                ),
                ("title", models.CharField(max_length=255, verbose_name="title")),
                ("description", models.TextField(blank=True, verbose_name="description")),
                (
                    "file_url",
                    models.URLField(
                        blank=True,
                        help_text="URL del PDF o recurso de la guía",
                        max_length=500,
                        verbose_name="file URL",
                    ),
                ),
                ("order", models.PositiveIntegerField(default=0, verbose_name="order")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
            ],
            options={
                "verbose_name": "Erasmus destination guide",
                "verbose_name_plural": "Erasmus destination guides",
                "ordering": ["destination_slug", "order", "id"],
            },
        ),
    ]
