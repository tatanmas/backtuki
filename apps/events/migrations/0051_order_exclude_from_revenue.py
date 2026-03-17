# Order: exclude_from_revenue (manual exclude from revenue and payables)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0050_order_is_sandbox_and_deleted_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="exclude_from_revenue",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="If True, this order is excluded from revenue, analytics and organizer payables (test, sandbox, cortesía, historical).",
                verbose_name="exclude from revenue",
            ),
        ),
    ]
