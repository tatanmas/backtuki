# Generated manually: prefijo opcional para código público (ej. Tuki-PV-001).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0022_add_public_code_and_display_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="accommodation",
            name="public_code_prefix",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Optional prefix for public code (e.g. Tuki-PV → Tuki-PV-001). If blank, uses default tuqui{N}-{random}.",
                max_length=30,
                verbose_name="public code prefix",
            ),
        ),
    ]
