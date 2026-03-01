# Interested count boost: extra number added to displayed "interesados" for social proof

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0038_instance_instructions_whatsapp"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmusactivityinstance",
            name="interested_count_boost",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Extra number added to real inscritos count for display (social proof).",
                verbose_name="interested count boost",
            ),
        ),
    ]
