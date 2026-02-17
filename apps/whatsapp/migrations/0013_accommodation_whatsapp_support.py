# Generated migration: WhatsApp support for accommodation reservations

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0002_accommodation_reservation"),
        ("whatsapp", "0012_operator_nullable_last_message_preview"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappreservationrequest",
            name="accommodation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_reservations",
                to="accommodations.accommodation",
                verbose_name="Accommodation",
                help_text="Accommodation for WhatsApp reservation (when product is accommodation)",
            ),
        ),
        migrations.AddField(
            model_name="whatsappreservationrequest",
            name="linked_accommodation_reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_requests",
                to="accommodations.accommodationreservation",
                verbose_name="Linked Accommodation Reservation",
            ),
        ),
        migrations.AlterField(
            model_name="whatsappreservationcode",
            name="experience",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="whatsapp_reservation_codes",
                to="experiences.experience",
                verbose_name="Experience",
                help_text="Experience for experience codes. Null when accommodation is set.",
            ),
        ),
        migrations.AddField(
            model_name="whatsappreservationcode",
            name="accommodation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="whatsapp_reservation_codes",
                to="accommodations.accommodation",
                verbose_name="Accommodation",
                help_text="Accommodation for accommodation codes. Null when experience is set.",
            ),
        ),
        migrations.CreateModel(
            name="AccommodationOperatorBinding",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("priority", models.IntegerField(default=0, help_text="Lower number = higher priority", verbose_name="Priority")),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                (
                    "accommodation",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operator_bindings", to="accommodations.accommodation", verbose_name="Accommodation"),
                ),
                (
                    "tour_operator",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="accommodation_bindings", to="whatsapp.touroperator", verbose_name="Tour Operator"),
                ),
            ],
            options={
                "verbose_name": "Accommodation-Operator Binding",
                "verbose_name_plural": "Accommodation-Operator Bindings",
                "ordering": ["accommodation", "priority"],
            },
        ),
        migrations.CreateModel(
            name="AccommodationGroupBinding",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("is_override", models.BooleanField(default=False, verbose_name="Override Default")),
                (
                    "accommodation",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_group_bindings", to="accommodations.accommodation", verbose_name="Accommodation"),
                ),
                (
                    "tour_operator",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="accommodation_group_bindings", to="whatsapp.touroperator", verbose_name="Tour Operator"),
                ),
                (
                    "whatsapp_group",
                    models.ForeignKey(blank=True, limit_choices_to={"type": "group"}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="accommodation_bindings", to="whatsapp.whatsappchat", verbose_name="WhatsApp Group"),
                ),
            ],
            options={
                "verbose_name": "Accommodation-Group Binding",
                "verbose_name_plural": "Accommodation-Group Bindings",
            },
        ),
        migrations.AddConstraint(
            model_name="accommodationoperatorbinding",
            constraint=models.UniqueConstraint(fields=("accommodation", "tour_operator"), name="whatsapp_accommodationoperator_accommo_unique"),
        ),
        migrations.AddConstraint(
            model_name="accommodationgroupbinding",
            constraint=models.UniqueConstraint(fields=("accommodation", "whatsapp_group"), name="whatsapp_accommodationgroup_accommo_unique"),
        ),
        migrations.AddIndex(
            model_name="accommodationgroupbinding",
            index=models.Index(fields=["accommodation", "is_active"], name="whatsapp_accommodati_accommo_idx"),
        ),
        migrations.AddIndex(
            model_name="accommodationgroupbinding",
            index=models.Index(fields=["whatsapp_group", "is_active"], name="whatsapp_accommodati_whatsap_idx"),
        ),
    ]
