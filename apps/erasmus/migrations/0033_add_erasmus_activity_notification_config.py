# Generated manually: notify group when someone signs up for an Erasmus activity

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0032_add_erasmus_partner_notification_config"),
        ("whatsapp", "0016_remove_accommodationgroupbinding_whatsapp_accommodationgroup_accommo_unique_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErasmusActivityNotificationConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
                ("activity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_configs", to="erasmus.erasmusactivity", verbose_name="Erasmus activity")),
                ("whatsapp_chat", models.ForeignKey(help_text="Group to receive notifications; must be type=group.", on_delete=django.db.models.deletion.CASCADE, related_name="+", to="whatsapp.whatsappchat", verbose_name="WhatsApp group")),
            ],
            options={
                "verbose_name": "Erasmus activity notification config",
                "verbose_name_plural": "Erasmus activity notification configs",
                "ordering": ["activity__display_order", "activity__title_es"],
            },
        ),
        migrations.AddConstraint(
            model_name="erasmusactivitynotificationconfig",
            constraint=models.UniqueConstraint(fields=("activity", "whatsapp_chat"), name="erasmus_activity_notif_config_activity_chat_unique"),
        ),
    ]
