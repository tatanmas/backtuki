# Generated migration: country, extra_data, ErasmusExtraField

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmuslead",
            name="country",
            field=models.CharField(
                blank=True,
                help_text="Country of origin or residence (país)",
                max_length=100,
                verbose_name="country",
            ),
        ),
        migrations.AddField(
            model_name="erasmuslead",
            name="extra_data",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Answers to dynamic extra questions (ErasmusExtraField)",
                verbose_name="extra data",
            ),
        ),
        migrations.CreateModel(
            name="ErasmusExtraField",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=255, verbose_name="label")),
                (
                    "field_key",
                    models.SlugField(
                        help_text="Unique key for this field (e.g. motivacion_erasmus)",
                        max_length=80,
                        unique=True,
                        verbose_name="field key",
                    ),
                ),
                ("type", models.CharField(choices=[("text", "Text"), ("email", "Email"), ("phone", "Phone"), ("number", "Number"), ("select", "Select"), ("multiselect", "Multiple select"), ("checkbox", "Checkbox"), ("radio", "Radio"), ("date", "Date"), ("textarea", "Text area"), ("url", "URL")], max_length=20, verbose_name="type")),
                ("required", models.BooleanField(default=False, verbose_name="required")),
                ("placeholder", models.CharField(blank=True, max_length=255, verbose_name="placeholder")),
                ("help_text", models.TextField(blank=True, verbose_name="help text")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="order")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
                (
                    "options",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="For select/radio: list of {value, label}",
                        verbose_name="options",
                    ),
                ),
            ],
            options={
                "verbose_name": "Erasmus extra field",
                "verbose_name_plural": "Erasmus extra fields",
                "ordering": ["order", "id"],
            },
        ),
    ]
