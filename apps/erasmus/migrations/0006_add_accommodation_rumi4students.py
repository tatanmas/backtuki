# Generated migration: has_accommodation_in_chile, wants_rumi4students_contact

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0005_erasmuslead_city"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmuslead",
            name="has_accommodation_in_chile",
            field=models.BooleanField(
                default=False,
                help_text="Si ya tiene alojamiento en Chile",
                verbose_name="has accommodation in Chile",
            ),
        ),
        migrations.AddField(
            model_name="erasmuslead",
            name="wants_rumi4students_contact",
            field=models.BooleanField(
                default=False,
                help_text="Quiere que lo contactemos para ayudarle a encontrar alojamiento con agencias partner Rumi4Students",
                verbose_name="wants Rumi4Students contact",
            ),
        ),
    ]
