# Erasmus activity reviews (per instance) + review_token on public link

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0039_erasmusactivityinstance_interested_count_boost"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmusactivitypubliclink",
            name="review_token",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Token for public review link (students leave a review for an instance).",
                max_length=64,
                null=True,
                unique=True,
                verbose_name="review token",
            ),
        ),
        migrations.CreateModel(
            name="ErasmusActivityReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author_name",
                    models.CharField(
                        help_text="Name shown with the review (e.g. from Erasmus profile or form).",
                        max_length=255,
                        verbose_name="author name",
                    ),
                ),
                (
                    "author_origin",
                    models.CharField(
                        blank=True,
                        help_text="Where they are from (e.g. country/city).",
                        max_length=255,
                        verbose_name="author origin",
                    ),
                ),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        help_text="1-5 stars satisfaction.",
                        validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)],
                        verbose_name="rating",
                    ),
                ),
                (
                    "body",
                    models.TextField(help_text="Review text / comment.", verbose_name="body"),
                ),
                (
                    "instance",
                    models.ForeignKey(
                        help_text="The activity instance (date) this review is for.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reviews",
                        to="erasmus.erasmusactivityinstance",
                        verbose_name="instance",
                    ),
                ),
                (
                    "lead",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional link to Erasmus lead if identified (e.g. from magic link).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activity_reviews",
                        to="erasmus.erasmuslead",
                        verbose_name="lead",
                    ),
                ),
            ],
            options={
                "verbose_name": "Erasmus activity review",
                "verbose_name_plural": "Erasmus activity reviews",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="erasmusactivityreview",
            index=models.Index(fields=["instance"], name="erasmus_era_instance_7a0b0d_idx"),
        ),
    ]
