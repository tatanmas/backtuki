# Erasmus activity paid + inscription payments (revenue tracking)

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0043_erasmuswhatsappgroup_image_url_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmusactivity",
            name="is_paid",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="If set, inscriptions can be marked as paid from the inscritos view; revenue is tracked.",
                verbose_name="paid activity",
            ),
        ),
        migrations.AddField(
            model_name="erasmusactivity",
            name="price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Suggested price per inscription (e.g. for prefilling when marking as paid).",
                max_digits=12,
                null=True,
                verbose_name="price",
            ),
        ),
        migrations.CreateModel(
            name="ErasmusActivityInscriptionPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Amount paid for this inscription.",
                        max_digits=12,
                        verbose_name="amount",
                    ),
                ),
                (
                    "payment_method",
                    models.CharField(
                        choices=[
                            ("efectivo", "Efectivo"),
                            ("transferencia", "Transferencia"),
                            ("tarjeta", "Tarjeta"),
                            ("mercadopago", "Mercado Pago"),
                            ("paypal", "PayPal"),
                            ("other", "Otro"),
                        ],
                        default="efectivo",
                        max_length=32,
                        verbose_name="payment method",
                    ),
                ),
                (
                    "paid_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        help_text="When the payment was recorded.",
                        verbose_name="paid at",
                    ),
                ),
                (
                    "instance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inscription_payments",
                        to="erasmus.erasmusactivityinstance",
                        verbose_name="activity instance",
                    ),
                ),
                (
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activity_inscription_payments",
                        to="erasmus.erasmuslead",
                        verbose_name="lead",
                    ),
                ),
            ],
            options={
                "verbose_name": "Erasmus activity inscription payment",
                "verbose_name_plural": "Erasmus activity inscription payments",
                "ordering": ["-paid_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="erasmusactivityinscriptionpayment",
            constraint=models.UniqueConstraint(
                fields=("lead", "instance"),
                name="erasmus_inscription_payment_unique_lead_instance",
            ),
        ),
        migrations.AddIndex(
            model_name="erasmusactivityinscriptionpayment",
            index=models.Index(fields=["instance"], name="erasmus_era_instance_8a1f0c_idx"),
        ),
    ]
