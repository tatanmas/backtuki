# Generated migration: ErasmusActivity and ErasmusActivityInstance

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0013_add_slide_caption"),
        ("experiences", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErasmusActivity",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title_es", models.CharField(max_length=255, verbose_name="title Spanish")),
                ("title_en", models.CharField(blank=True, max_length=255, verbose_name="title English")),
                ("slug", models.SlugField(db_index=True, max_length=255, unique=True, verbose_name="slug")),
                ("description_es", models.TextField(blank=True, verbose_name="description Spanish")),
                ("description_en", models.TextField(blank=True, verbose_name="description English")),
                ("short_description_es", models.CharField(blank=True, max_length=500, verbose_name="short description Spanish")),
                ("short_description_en", models.CharField(blank=True, max_length=500, verbose_name="short description English")),
                ("location", models.CharField(blank=True, max_length=255, verbose_name="location")),
                (
                    "images",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of image URLs; images[0] = main image (same convention as Experience)",
                        verbose_name="images",
                    ),
                ),
                ("display_order", models.PositiveIntegerField(db_index=True, default=0, verbose_name="display order")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
                (
                    "experience",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="erasmus_activities",
                        to="experiences.experience",
                        verbose_name="experience",
                    ),
                ),
            ],
            options={
                "verbose_name": "Erasmus activity",
                "verbose_name_plural": "Erasmus activities",
                "ordering": ["display_order", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="ErasmusActivityInstance",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "scheduled_date",
                    models.DateField(blank=True, null=True, verbose_name="scheduled date"),
                ),
                (
                    "scheduled_month",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="scheduled month",
                    ),
                ),
                (
                    "scheduled_year",
                    models.IntegerField(blank=True, null=True, verbose_name="scheduled year"),
                ),
                (
                    "scheduled_label_es",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="scheduled label Spanish",
                    ),
                ),
                (
                    "scheduled_label_en",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="scheduled label English",
                    ),
                ),
                ("display_order", models.PositiveIntegerField(default=0, verbose_name="display order")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
                (
                    "activity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="instances",
                        to="erasmus.erasmusactivity",
                        verbose_name="activity",
                    ),
                ),
            ],
            options={
                "verbose_name": "Erasmus activity instance",
                "verbose_name_plural": "Erasmus activity instances",
                "ordering": ["display_order", "scheduled_date", "scheduled_year", "scheduled_month", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="erasmusactivity",
            index=models.Index(fields=["slug"], name="erasmus_act_slug_idx"),
        ),
        migrations.AddIndex(
            model_name="erasmusactivity",
            index=models.Index(fields=["is_active", "display_order"], name="erasmus_act_active_ord_idx"),
        ),
        migrations.AddIndex(
            model_name="erasmusactivityinstance",
            index=models.Index(fields=["activity", "scheduled_date"], name="erasmus_inst_act_date_idx"),
        ),
        migrations.AddIndex(
            model_name="erasmusactivityinstance",
            index=models.Index(fields=["is_active"], name="erasmus_inst_active_idx"),
        ),
    ]
