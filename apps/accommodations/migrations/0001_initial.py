# Generated migration for Accommodation and AccommodationReview
# Ejecutar migraciones con Docker: docker exec tuki-backend python manage.py migrate

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organizers", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Accommodation",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255, verbose_name="title")),
                ("slug", models.SlugField(db_index=True, max_length=255, unique=True, verbose_name="slug")),
                ("description", models.TextField(blank=True, verbose_name="description")),
                ("short_description", models.CharField(blank=True, max_length=500, verbose_name="short description")),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published"), ("cancelled", "Cancelled")],
                        db_index=True,
                        default="draft",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                (
                    "property_type",
                    models.CharField(
                        choices=[
                            ("cabin", "Cabin"),
                            ("house", "House"),
                            ("apartment", "Apartment"),
                            ("hotel", "Hotel"),
                            ("hostel", "Hostel"),
                            ("villa", "Villa"),
                            ("other", "Other"),
                        ],
                        default="cabin",
                        max_length=20,
                        verbose_name="property type",
                    ),
                ),
                ("location_name", models.CharField(blank=True, max_length=255, verbose_name="location name")),
                ("location_address", models.TextField(blank=True, verbose_name="address")),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name="latitude")),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name="longitude")),
                ("country", models.CharField(default="Chile", max_length=255, verbose_name="country")),
                ("city", models.CharField(blank=True, max_length=255, verbose_name="city / region")),
                (
                    "guests",
                    models.PositiveIntegerField(
                        default=2,
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="max guests",
                    ),
                ),
                (
                    "bedrooms",
                    models.PositiveIntegerField(
                        default=1,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="bedrooms",
                    ),
                ),
                (
                    "bathrooms",
                    models.PositiveIntegerField(
                        default=1,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="bathrooms",
                    ),
                ),
                (
                    "beds",
                    models.PositiveIntegerField(
                        blank=True,
                        default=1,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="beds",
                    ),
                ),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="price per night",
                    ),
                ),
                ("currency", models.CharField(default="CLP", max_length=3, verbose_name="currency")),
                ("amenities", models.JSONField(default=list, help_text="List of amenity strings", verbose_name="amenities")),
                ("not_amenities", models.JSONField(default=list, help_text="List of things not available", verbose_name="not available")),
                ("images", models.JSONField(default=list, verbose_name="image URLs")),
                ("gallery_media_ids", models.JSONField(default=list, help_text="UUIDs of MediaAsset for gallery", verbose_name="gallery media asset IDs")),
                (
                    "rating_avg",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        max_digits=2,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ],
                        verbose_name="average rating",
                    ),
                ),
                ("review_count", models.PositiveIntegerField(default=0, verbose_name="review count")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="deleted at")),
                (
                    "organizer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="accommodations",
                        to="organizers.organizer",
                        verbose_name="organizer",
                    ),
                ),
            ],
            options={
                "verbose_name": "Accommodation",
                "verbose_name_plural": "Accommodations",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AccommodationReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("author_name", models.CharField(max_length=255, verbose_name="author name")),
                ("author_location", models.CharField(blank=True, max_length=255, verbose_name="author location")),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ],
                        verbose_name="rating",
                    ),
                ),
                ("text", models.TextField(blank=True, verbose_name="review text")),
                ("review_date", models.DateField(blank=True, null=True, verbose_name="review date")),
                ("stay_type", models.CharField(blank=True, max_length=100, verbose_name="stay type")),
                ("host_reply", models.TextField(blank=True, verbose_name="host reply")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "accommodation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reviews",
                        to="accommodations.accommodation",
                        verbose_name="accommodation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Accommodation review",
                "verbose_name_plural": "Accommodation reviews",
                "ordering": ["-review_date", "-created_at"],
            },
        ),
    ]
