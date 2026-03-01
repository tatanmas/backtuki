# Order: erasmus_activity order kind and FK to ErasmusActivityPaymentLink

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0048_alter_order_order_kind"),
        ("erasmus", "0045_erasmusactivitypaymentlink"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="erasmus_activity_payment_link",
            field=models.OneToOneField(
                blank=True,
                help_text="Linked payment link for erasmus_activity orders. Null otherwise.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="order",
                to="erasmus.ErasmusActivityPaymentLink",
                verbose_name="Erasmus activity payment link",
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
                    ("erasmus_activity", "Erasmus Activity Order"),
                ],
                default="event",
                help_text="Domain this order belongs to: event tickets or experiences.",
                max_length=20,
                verbose_name="order kind",
            ),
        ),
    ]
