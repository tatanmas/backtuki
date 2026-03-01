# Generated manually: capacity (cupos) and is_agotado on ErasmusActivityInstance

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0033_add_erasmus_activity_notification_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmusactivityinstance",
            name="capacity",
            field=models.PositiveIntegerField(
                blank=True,
                db_index=True,
                help_text="Max participants; leave empty for unlimited.",
                null=True,
                verbose_name="capacity",
            ),
        ),
        migrations.AddField(
            model_name="erasmusactivityinstance",
            name="is_agotado",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="If set, no new sign-ups are accepted.",
                verbose_name="sold out",
            ),
        ),
    ]
