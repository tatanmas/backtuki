# Initial migration for car_rental app (CarRentalCompany, Car, CarBlockedDate, CarReservation)

import django.core.validators
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0009_alter_platformuptimeheartbeat_id_and_more"),
        ("organizers", "0019_add_payout_model"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CarRentalCompany",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255, verbose_name="name")),
                ("slug", models.SlugField(max_length=255, unique=True, db_index=True, verbose_name="slug")),
                ("short_description", models.CharField(blank=True, max_length=500, verbose_name="short description")),
                ("description", models.TextField(blank=True, verbose_name="description")),
                ("hero_media_id", models.UUIDField(blank=True, null=True, verbose_name="hero image from media library")),
                ("gallery_media_ids", models.JSONField(blank=True, default=list, verbose_name="gallery media asset IDs")),
                ("conditions", models.JSONField(blank=True, default=dict, verbose_name="conditions")),
                ("is_active", models.BooleanField(default=True, db_index=True, verbose_name="active")),
                ("country", models.CharField(blank=True, max_length=255, verbose_name="country")),
                ("city", models.CharField(blank=True, max_length=255, verbose_name="city")),
                (
                    "organizer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="car_rental_companies",
                        to="organizers.organizer",
                        verbose_name="organizer",
                    ),
                ),
            ],
            options={
                "verbose_name": "Car rental company",
                "verbose_name_plural": "Car rental companies",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Car",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255, verbose_name="title")),
                ("slug", models.SlugField(max_length=255, unique=True, db_index=True, verbose_name="slug")),
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
                    "price_per_day",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="price per day",
                    ),
                ),
                ("currency", models.CharField(default="CLP", max_length=3, verbose_name="currency")),
                ("pickup_time_default", models.CharField(blank=True, max_length=5, verbose_name="default pickup time")),
                ("return_time_default", models.CharField(blank=True, max_length=5, verbose_name="default return time")),
                ("included", models.JSONField(blank=True, default=list, verbose_name="included")),
                ("not_included", models.JSONField(blank=True, default=list, verbose_name="not included")),
                ("inherit_company_conditions", models.BooleanField(default=True, verbose_name="inherit company conditions")),
                ("conditions_override", models.JSONField(blank=True, default=dict, verbose_name="conditions override")),
                ("gallery_media_ids", models.JSONField(blank=True, default=list, verbose_name="gallery media asset IDs")),
                ("images", models.JSONField(blank=True, default=list, verbose_name="image URLs fallback")),
                (
                    "min_driver_age",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(18)],
                        verbose_name="minimum driver age",
                    ),
                ),
                (
                    "transmission",
                    models.CharField(
                        choices=[("manual", "Manual"), ("automatic", "Automatic")],
                        default="manual",
                        max_length=20,
                        blank=True,
                        verbose_name="transmission",
                    ),
                ),
                (
                    "seats",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="seats",
                    ),
                ),
                (
                    "bags",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="bags",
                    ),
                ),
                ("deleted_at", models.DateTimeField(blank=True, null=True, db_index=True, verbose_name="deleted at")),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cars",
                        to="car_rental.carrentalcompany",
                        verbose_name="company",
                    ),
                ),
            ],
            options={
                "verbose_name": "Car",
                "verbose_name_plural": "Cars",
                "ordering": ["company", "title"],
            },
        ),
        migrations.CreateModel(
            name="CarBlockedDate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True, verbose_name="date")),
                (
                    "car",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blocked_dates",
                        to="car_rental.car",
                        verbose_name="car",
                    ),
                ),
            ],
            options={
                "verbose_name": "Car blocked date",
                "verbose_name_plural": "Car blocked dates",
                "ordering": ["car", "date"],
                "unique_together": {("car", "date")},
            },
        ),
        migrations.CreateModel(
            name="CarReservation",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reservation_id", models.CharField(db_index=True, max_length=100, unique=True, verbose_name="reservation ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("paid", "Paid"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                            ("refunded", "Refunded"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                ("pickup_date", models.DateField(verbose_name="pickup date")),
                ("return_date", models.DateField(verbose_name="return date")),
                ("pickup_time", models.CharField(blank=True, max_length=5, verbose_name="pickup time")),
                ("return_time", models.CharField(blank=True, max_length=5, verbose_name="return time")),
                ("first_name", models.CharField(max_length=100, verbose_name="first name")),
                ("last_name", models.CharField(max_length=100, verbose_name="last name")),
                ("email", models.EmailField(max_length=254, verbose_name="email")),
                ("phone", models.CharField(blank=True, max_length=20, verbose_name="phone")),
                (
                    "total",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="total",
                    ),
                ),
                ("currency", models.CharField(default="CLP", max_length=3, verbose_name="currency")),
                ("paid_at", models.DateTimeField(blank=True, null=True, verbose_name="paid at")),
                (
                    "car",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservations",
                        to="car_rental.car",
                        verbose_name="car",
                    ),
                ),
                (
                    "flow",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="car_rental_reservations",
                        to="core.platformflow",
                        verbose_name="platform flow",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="car_rental_reservations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "verbose_name": "Car reservation",
                "verbose_name_plural": "Car reservations",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="car",
            index=models.Index(fields=["company", "status"], name="car_rental_c_company_7a0f0d_idx"),
        ),
        migrations.AddIndex(
            model_name="car",
            index=models.Index(fields=["slug"], name="car_rental_c_slug_8b2c4a_idx"),
        ),
        migrations.AddIndex(
            model_name="carblockeddate",
            index=models.Index(fields=["car", "date"], name="car_rental_c_car_id_2a1b5c_idx"),
        ),
        migrations.AddIndex(
            model_name="carreservation",
            index=models.Index(fields=["reservation_id"], name="car_rental_c_reserva_3d4e6f_idx"),
        ),
        migrations.AddIndex(
            model_name="carreservation",
            index=models.Index(fields=["car", "status"], name="car_rental_c_car_id_4e5f7a_idx"),
        ),
        migrations.AddIndex(
            model_name="carreservation",
            index=models.Index(fields=["pickup_date", "return_date"], name="car_rental_c_pickup__5f6a8b_idx"),
        ),
    ]
