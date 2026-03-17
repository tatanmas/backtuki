# Erasmus welcome message templates (editable from Super Admin)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0047_rename_erasmus_era_instanc_idx_erasmus_era_instanc_4f011d_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErasmusWelcomeMessageConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="updated at")),
                (
                    "config_key",
                    models.CharField(
                        default="default",
                        editable=False,
                        max_length=50,
                        unique=True,
                        verbose_name="config key",
                    ),
                ),
                (
                    "messages_by_locale",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='Dict locale -> template text, e.g. {"es": "Hola {first_name}...", "en": "Hi {first_name}..."}. Placeholders: first_name, link_plataforma, magic_link_url, email.',
                        verbose_name="messages by locale",
                    ),
                ),
            ],
            options={
                "verbose_name": "Erasmus welcome message config",
                "verbose_name_plural": "Erasmus welcome message configs",
            },
        ),
    ]
