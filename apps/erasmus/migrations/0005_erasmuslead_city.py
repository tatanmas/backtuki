# Generated migration: add city (ciudad de origen) to ErasmusLead

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0004_erasmusdestinationguide"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmuslead",
            name="city",
            field=models.CharField(
                blank=True,
                help_text="City of origin or residence (ciudad)",
                max_length=150,
                verbose_name="city",
            ),
        ),
    ]
