# Generated manually: public links (view inscritos / edit) for Erasmus activities

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0036_add_erasmus_activity_detail_layout"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErasmusActivityPublicLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("view_token", models.CharField(db_index=True, help_text="Token for public view link (list of inscritos).", max_length=64, unique=True, verbose_name="view token")),
                ("edit_token", models.CharField(db_index=True, help_text="Token for public edit link (same UI as superadmin, no auth).", max_length=64, unique=True, verbose_name="edit token")),
                ("links_enabled", models.BooleanField(db_index=True, default=True, help_text="When False, both public links return disabled/404.", verbose_name="links enabled")),
                ("activity", models.OneToOneField(on_delete=models.CASCADE, related_name="public_link", to="erasmus.erasmusactivity", verbose_name="activity")),
            ],
            options={
                "verbose_name": "Erasmus activity public link",
                "verbose_name_plural": "Erasmus activity public links",
            },
        ),
    ]
