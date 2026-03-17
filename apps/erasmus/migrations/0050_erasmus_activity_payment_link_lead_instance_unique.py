# UniqueConstraint (lead, instance) on ErasmusActivityPaymentLink for concurrent-safe get-or-create

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0049_alter_erasmuswelcomemessageconfig_created_at_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="erasmusactivitypaymentlink",
            constraint=models.UniqueConstraint(
                fields=("lead", "instance"),
                name="erasmus_activity_payment_link_lead_instance_unique",
            ),
        ),
    ]
