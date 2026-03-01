# Hotel model and Accommodation hotel/room inheritance fields

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0009_rentalhub_hero_media_gallery_media_ids"),
    ]

    operations = [
        migrations.CreateModel(
            name="Hotel",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("slug", models.SlugField(db_index=True, max_length=255, unique=True, verbose_name="slug")),
                ("name", models.CharField(max_length=255, verbose_name="name")),
                ("short_description", models.CharField(blank=True, max_length=500, verbose_name="short description")),
                ("description", models.TextField(blank=True, verbose_name="description")),
                (
                    "hero_media_id",
                    models.UUIDField(
                        blank=True,
                        help_text="MediaAsset UUID for hero image (superadmin library)",
                        null=True,
                        verbose_name="hero image from media library",
                    ),
                ),
                (
                    "gallery_media_ids",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of MediaAsset UUIDs for the hotel gallery (superadmin library)",
                        verbose_name="gallery media asset IDs",
                    ),
                ),
                ("meta_title", models.CharField(blank=True, max_length=255, verbose_name="meta title (SEO)")),
                ("meta_description", models.CharField(blank=True, max_length=500, verbose_name="meta description (SEO)")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
                ("location_name", models.CharField(blank=True, max_length=255, verbose_name="location name")),
                ("location_address", models.TextField(blank=True, verbose_name="address")),
                ("city", models.CharField(blank=True, max_length=255, verbose_name="city / region")),
                ("country", models.CharField(default="Chile", max_length=255, verbose_name="country")),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        verbose_name="latitude",
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        max_digits=9,
                        null=True,
                        verbose_name="longitude",
                    ),
                ),
                (
                    "amenities",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of amenity strings; rooms can inherit these.",
                        verbose_name="amenities",
                    ),
                ),
                (
                    "external_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Optional mapping for channel manager integration.",
                        max_length=255,
                        verbose_name="external ID for channel manager",
                    ),
                ),
            ],
            options={
                "verbose_name": "Hotel",
                "verbose_name_plural": "Hotels",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="accommodation",
            name="hotel",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rooms",
                to="accommodations.hotel",
                verbose_name="hotel",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="inherit_location_from_hotel",
            field=models.BooleanField(
                default=True,
                help_text="When True, public API uses hotel location when room has no own location.",
                verbose_name="inherit location from hotel",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="inherit_amenities_from_hotel",
            field=models.BooleanField(
                default=True,
                help_text="When True, public API merges hotel amenities with room amenities.",
                verbose_name="inherit amenities from hotel",
            ),
        ),
        migrations.AddField(
            model_name="accommodation",
            name="room_type_code",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="e.g. STD, DBL, SUITE for future channel manager integration.",
                max_length=30,
                verbose_name="room type code for channel manager",
            ),
        ),
    ]
