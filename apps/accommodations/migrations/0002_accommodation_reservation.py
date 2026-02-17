# Generated migration: AccommodationReservation for WhatsApp/payment flow

import uuid
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0001_initial"),
        ("users", "__first__"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccommodationReservation",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reservation_id", models.CharField(db_index=True, max_length=100, unique=True, verbose_name="reservation ID")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("paid", "Paid"), ("cancelled", "Cancelled"), ("expired", "Expired"), ("refunded", "Refunded")], db_index=True, default="pending", max_length=20, verbose_name="status")),
                ("check_in", models.DateField(verbose_name="check-in")),
                ("check_out", models.DateField(verbose_name="check-out")),
                ("guests", models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)], verbose_name="guests")),
                ("first_name", models.CharField(max_length=100, verbose_name="first name")),
                ("last_name", models.CharField(max_length=100, verbose_name="last name")),
                ("email", models.EmailField(max_length=254, verbose_name="email")),
                ("phone", models.CharField(blank=True, max_length=20, verbose_name="phone")),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)], verbose_name="total")),
                ("currency", models.CharField(default="CLP", max_length=3, verbose_name="currency")),
                ("paid_at", models.DateTimeField(blank=True, null=True, verbose_name="paid at")),
                (
                    "accommodation",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reservations", to="accommodations.accommodation", verbose_name="accommodation"),
                ),
                (
                    "user",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="accommodation_reservations", to="users.user", verbose_name="user"),
                ),
            ],
            options={
                "verbose_name": "Accommodation reservation",
                "verbose_name_plural": "Accommodation reservations",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="accommodationreservation",
            index=models.Index(fields=["reservation_id"], name="accommodati_reserva_6a0b0d_idx"),
        ),
        migrations.AddIndex(
            model_name="accommodationreservation",
            index=models.Index(fields=["accommodation", "status"], name="accommodati_accommo_8b2c1e_idx"),
        ),
        migrations.AddIndex(
            model_name="accommodationreservation",
            index=models.Index(fields=["check_in", "check_out"], name="accommodati_check_i_9d3f2a_idx"),
        ),
    ]
