# Central de arrendamiento: RentalHub, campos en Accommodation, AccommodationBlockedDate

import uuid
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0004_add_flow_to_accommodation_reservation"),
    ]

    operations = [
        migrations.CreateModel(
            name="RentalHub",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("slug", models.SlugField(db_index=True, max_length=255, unique=True, verbose_name="slug")),
                ("name", models.CharField(max_length=255, verbose_name="name")),
                ("short_description", models.CharField(blank=True, max_length=500, verbose_name="short description")),
                ("description", models.TextField(blank=True, verbose_name="description")),
                ("hero_image", models.URLField(blank=True, max_length=500, verbose_name="hero image URL")),
                (
                    "gallery",
                    models.JSONField(
                        default=list,
                        help_text="List of image URLs for the hub gallery",
                        verbose_name="gallery image URLs",
                    ),
                ),
                ("meta_title", models.CharField(blank=True, max_length=255, verbose_name="meta title (SEO)")),
                ("meta_description", models.CharField(blank=True, max_length=500, verbose_name="meta description (SEO)")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
            ],
            options={
                "verbose_name": "Rental hub",
                "verbose_name_plural": "Rental hubs",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="accommodation",
            name="rental_hub",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="accommodations",
                to="accommodations.rentalhub",
                verbose_name="rental hub",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="unit_type",
            field=models.CharField(
                blank=True,
                choices=[("A1", "A1"), ("A2", "A2"), ("B", "B"), ("C", "C")],
                db_index=True,
                help_text="Tipo de departamento (A1, A2, B, C)",
                max_length=10,
                verbose_name="unit type",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="tower",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Torre (A, B)",
                max_length=10,
                verbose_name="tower",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="floor",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Piso",
                verbose_name="floor",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="unit_number",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Número de departamento (ej. 101, 803)",
                max_length=20,
                verbose_name="unit number",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="square_meters",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Metraje total en m²",
                max_digits=8,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="square meters",
            ),
        ),
        migrations.CreateModel(
            name="AccommodationBlockedDate",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("date", models.DateField(db_index=True, verbose_name="date")),
                (
                    "accommodation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blocked_dates",
                        to="accommodations.accommodation",
                        verbose_name="accommodation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Accommodation blocked date",
                "verbose_name_plural": "Accommodation blocked dates",
                "ordering": ["accommodation", "date"],
                "unique_together": {("accommodation", "date")},
            },
        ),
        migrations.AddIndex(
            model_name="accommodationblockeddate",
            index=models.Index(fields=["accommodation", "date"], name="accommodati_accommo_6b0b0d_idx"),
        ),
    ]
