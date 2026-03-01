# Order support for car rental reservations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("car_rental", "0001_initial_car_rental"),
        ("events", "0046_alter_order_experience_reservation_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="car_rental_reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="car_rental.carreservation",
                verbose_name="car rental reservation",
                help_text="Linked car rental reservation for car_rental orders. Null otherwise.",
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="order_kind",
            field=models.CharField(
                choices=[
                    ("event", "Event Order"),
                    ("experience", "Experience Order"),
                    ("accommodation", "Accommodation Order"),
                    ("car_rental", "Car Rental Order"),
                ],
                default="event",
                help_text="Domain this order belongs to: event tickets, experiences, accommodations, or car rentals.",
                max_length=20,
                verbose_name="order kind",
            ),
        ),
    ]
