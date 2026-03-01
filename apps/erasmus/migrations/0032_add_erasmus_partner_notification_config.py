# Generated manually: ErasmusPartnerNotificationConfig for Rumi (and future) WhatsApp notifications

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0031_add_budget_trip_budget_stay"),
        ("whatsapp", "0016_remove_accommodationgroupbinding_whatsapp_accommodationgroup_accommo_unique_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErasmusPartnerNotificationConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("slug", models.SlugField(db_index=True, help_text="Identifier for this notification type (e.g. rumi_housing)", max_length=80, unique=True, verbose_name="slug")),
                ("name", models.CharField(help_text="Display name (e.g. Rumi – Housing)", max_length=255, verbose_name="name")),
                ("is_active", models.BooleanField(db_index=True, default=True, help_text="If disabled, no notifications are sent.", verbose_name="active")),
                ("description", models.TextField(blank=True, help_text="Optional: what events trigger this notification.", verbose_name="description")),
                ("whatsapp_chat", models.ForeignKey(blank=True, help_text="Group to receive notifications; must be type=group.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="whatsapp.whatsappchat", verbose_name="WhatsApp group")),
            ],
            options={
                "verbose_name": "Erasmus partner notification config",
                "verbose_name_plural": "Erasmus partner notification configs",
                "ordering": ["slug"],
            },
        ),
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model("erasmus", "ErasmusPartnerNotificationConfig").objects.get_or_create(
                slug="rumi_housing",
                defaults={"name": "Rumi – Housing", "is_active": False, "description": "Notificar cuando un registro Erasmus requiere housing (wants_rumi4students_contact)."},
            ),
            migrations.RunPython.noop,
        ),
    ]
