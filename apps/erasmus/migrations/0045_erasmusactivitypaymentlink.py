# Erasmus activity payment link (pay online via platform)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0044_erasmus_activity_paid_and_inscription_payment"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErasmusActivityPaymentLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Amount to pay for this inscription.",
                        max_digits=12,
                        verbose_name="amount",
                    ),
                ),
                ("currency", models.CharField(default="CLP", max_length=3, verbose_name="currency")),
                (
                    "token",
                    models.CharField(
                        db_index=True,
                        help_text="URL-safe token for the payment link.",
                        max_length=64,
                        unique=True,
                        verbose_name="token",
                    ),
                ),
                ("expires_at", models.DateTimeField(blank=True, null=True, verbose_name="expires at")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="created at")),
                (
                    "instance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payment_links",
                        to="erasmus.erasmusactivityinstance",
                        verbose_name="activity instance",
                    ),
                ),
                (
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activity_payment_links",
                        to="erasmus.erasmuslead",
                        verbose_name="lead",
                    ),
                ),
            ],
            options={
                "verbose_name": "Erasmus activity payment link",
                "verbose_name_plural": "Erasmus activity payment links",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="erasmusactivitypaymentlink",
            index=models.Index(fields=["instance"], name="erasmus_era_instanc_idx"),
        ),
    ]
