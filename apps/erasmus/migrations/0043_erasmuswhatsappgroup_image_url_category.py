# Generated manually: image_url and category for ErasmusWhatsAppGroup

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0042_merge_20260223_0519"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmuswhatsappgroup",
            name="image_url",
            field=models.URLField(
                blank=True,
                help_text="Optional: image to show for the group (e.g. group photo).",
                max_length=500,
                verbose_name="image URL",
            ),
        ),
        migrations.AddField(
            model_name="erasmuswhatsappgroup",
            name="category",
            field=models.CharField(
                choices=[("university", "University groups"), ("tuki", "Tuki groups")],
                db_index=True,
                default="tuki",
                help_text="University groups vs Tuki groups for display sections.",
                max_length=20,
                verbose_name="category",
            ),
        ),
    ]
