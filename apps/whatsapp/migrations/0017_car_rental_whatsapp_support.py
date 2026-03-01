# Car rental WhatsApp support: car + linked_car_rental_reservation on Request, car on Code, CarOperatorBinding, CarGroupBinding

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("car_rental", "0001_initial_car_rental"),
        ("whatsapp", "0016_remove_accommodationgroupbinding_whatsapp_accommodationgroup_accommo_unique_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappreservationrequest",
            name="car",
            field=models.ForeignKey(
                blank=True,
                help_text="Car for WhatsApp reservation (when product is car_rental)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_reservations",
                to="car_rental.car",
                verbose_name="Car",
            ),
        ),
        migrations.AddField(
            model_name="whatsappreservationrequest",
            name="linked_car_rental_reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_requests",
                to="car_rental.carreservation",
                verbose_name="Linked Car Rental Reservation",
            ),
        ),
        migrations.AddField(
            model_name="whatsappreservationcode",
            name="car",
            field=models.ForeignKey(
                blank=True,
                help_text="Car for car_rental codes. Null when experience/accommodation is set.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="whatsapp_reservation_codes",
                to="car_rental.car",
                verbose_name="Car",
            ),
        ),
        migrations.CreateModel(
            name="CarOperatorBinding",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("priority", models.IntegerField(default=0, help_text="Lower number = higher priority", verbose_name="Priority")),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("car", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operator_bindings", to="car_rental.car", verbose_name="Car")),
                ("tour_operator", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="car_bindings", to="whatsapp.touroperator", verbose_name="Tour Operator")),
            ],
            options={
                "verbose_name": "Car-Operator Binding",
                "verbose_name_plural": "Car-Operator Bindings",
                "ordering": ["car", "priority"],
                "unique_together": {("car", "tour_operator")},
            },
        ),
        migrations.CreateModel(
            name="CarGroupBinding",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("is_override", models.BooleanField(default=False, verbose_name="Override Default")),
                ("car", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_group_bindings", to="car_rental.car", verbose_name="Car")),
                ("tour_operator", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="car_group_bindings", to="whatsapp.touroperator", verbose_name="Tour Operator")),
                ("whatsapp_group", models.ForeignKey(blank=True, limit_choices_to={"type": "group"}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="car_bindings", to="whatsapp.whatsappchat", verbose_name="WhatsApp Group")),
            ],
            options={
                "verbose_name": "Car-Group Binding",
                "verbose_name_plural": "Car-Group Bindings",
                "unique_together": {("car", "whatsapp_group")},
                "indexes": [
                    models.Index(fields=["car", "is_active"], name="whatsapp_car_car_is_act_ix"),
                    models.Index(fields=["whatsapp_group", "is_active"], name="whatsapp_car_group_is_act_ix"),
                ],
            },
        ),
    ]
