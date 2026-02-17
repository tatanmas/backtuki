# Migration: interested_experiences for Erasmus timeline experiences

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0007_add_consent_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmuslead",
            name="interested_experiences",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of Erasmus timeline experience IDs the lead is interested in",
                verbose_name="interested experiences",
            ),
        ),
    ]
