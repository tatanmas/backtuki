# Order: is_sandbox (exclude from revenue) and deleted_at (soft delete / trash)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0049_order_erasmus_activity_payment_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="is_sandbox",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="True if payment was made in sandbox mode; do not count in revenue.",
                verbose_name="sandbox",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="deleted_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="When set, order is in trash and excluded from revenue and default lists.",
                null=True,
                verbose_name="deleted at",
            ),
        ),
    ]
