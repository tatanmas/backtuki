# Generated manually: detail_layout on ErasmusActivity for template selection (default / two_column)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0035_remove_budget_trip"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmusactivity",
            name="detail_layout",
            field=models.CharField(
                choices=[
                    ("default", "Default (single column, gallery on top)"),
                    ("two_column", "Two columns (photos on one side, info on the other)"),
                ],
                default="default",
                help_text="Template for the activity detail page on desktop.",
                max_length=20,
                verbose_name="detail page layout",
            ),
        ),
    ]
