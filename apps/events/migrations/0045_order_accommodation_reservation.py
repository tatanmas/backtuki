# Generated migration: Order support for accommodation reservations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0002_accommodation_reservation"),
        ("events", "0044_add_complimentary_tickets"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="accommodation_reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="accommodations.accommodationreservation",
                verbose_name="accommodation reservation",
                help_text="Linked accommodation reservation for accommodation orders. Null otherwise.",
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
                ],
                default="event",
                help_text="Domain this order belongs to: event tickets, experiences, or accommodations.",
                max_length=20,
                verbose_name="order kind",
            ),
        ),
    ]
