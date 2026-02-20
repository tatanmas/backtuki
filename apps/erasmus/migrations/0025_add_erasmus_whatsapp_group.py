# Generated manually: ErasmusWhatsAppGroup for superadmin-managed groups (name + link)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0024_erasmuslead_is_suspended"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErasmusWhatsAppGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Display name of the group", max_length=255, verbose_name="name")),
                ("link", models.URLField(help_text="WhatsApp group invite URL (e.g. https://chat.whatsapp.com/...)", max_length=500, verbose_name="link")),
                ("order", models.PositiveIntegerField(db_index=True, default=0, verbose_name="order")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
            ],
            options={
                "verbose_name": "Erasmus WhatsApp group",
                "verbose_name_plural": "Erasmus WhatsApp groups",
                "ordering": ["order", "id"],
            },
        ),
    ]
