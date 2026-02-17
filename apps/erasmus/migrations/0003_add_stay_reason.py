# Generated migration: stay_reason, stay_reason_detail; university/degree optional

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0002_country_extra_data_erasmusextrafield"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmuslead",
            name="stay_reason",
            field=models.CharField(
                choices=[
                    ("university", "Intercambio / Erasmus (universidad)"),
                    ("practicas", "Prácticas / Internship"),
                    ("other", "Otro"),
                ],
                default="university",
                help_text="Qué viene a hacer: universidad, prácticas u otro",
                max_length=20,
                verbose_name="reason for stay",
            ),
        ),
        migrations.AddField(
            model_name="erasmuslead",
            name="stay_reason_detail",
            field=models.CharField(
                blank=True,
                help_text="Ej. dónde hará prácticas o descripción si eligió otro",
                max_length=500,
                verbose_name="reason detail",
            ),
        ),
        migrations.AlterField(
            model_name="erasmuslead",
            name="university",
            field=models.CharField(blank=True, max_length=255, verbose_name="university"),
        ),
        migrations.AlterField(
            model_name="erasmuslead",
            name="degree",
            field=models.CharField(blank=True, max_length=255, verbose_name="degree / career"),
        ),
    ]
