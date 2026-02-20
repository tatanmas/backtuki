# Generated manually: add is_suspended to ErasmusLead

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0023_erasmuslocalpartner_asset_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmuslead",
            name="is_suspended",
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text="Si está suspendido, no aparece en comunidad y no puede usar enlaces de acceso",
                verbose_name="suspended",
            ),
        ),
    ]
