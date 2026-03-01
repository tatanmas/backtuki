# Remove budget_trip; form only asks for budget_stay (travel during exchange)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0034_instance_capacity_and_agotado"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="erasmuslead",
            name="budget_trip",
        ),
    ]
