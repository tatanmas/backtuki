# ErasmusActivityExtraField (per-activity form fields) and ErasmusActivityInstanceRegistration (lead+instance+extra_data)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0052_payment_link_sent_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="ErasmusActivityExtraField",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=255, verbose_name="label")),
                (
                    "field_key",
                    models.SlugField(
                        help_text="Unique key for this field (e.g. numero_ruta, pasaporte). Use in messages as {{field_key}}.",
                        max_length=80,
                        verbose_name="field key",
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("text", "Text"),
                            ("email", "Email"),
                            ("phone", "Phone"),
                            ("number", "Number"),
                            ("select", "Select"),
                            ("multiselect", "Multiple select"),
                            ("checkbox", "Checkbox"),
                            ("radio", "Radio"),
                            ("date", "Date"),
                            ("textarea", "Text area"),
                            ("url", "URL"),
                        ],
                        max_length=20,
                        verbose_name="type",
                    ),
                ),
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
                (
                    "activity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extra_fields",
                        to="erasmus.erasmusactivity",
                        verbose_name="activity",
                    ),
                ),
            ],
            options={
                "verbose_name": "Erasmus activity extra field",
                "verbose_name_plural": "Erasmus activity extra fields",
                "ordering": ["order", "id"],
                "unique_together": {("activity", "field_key")},
            },
        ),
        migrations.CreateModel(
            name="ErasmusActivityInstanceRegistration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "extra_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Answers to activity extra fields: {field_key: value}.",
                        verbose_name="extra data",
                    ),
                ),
                (
                    "instance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registrations",
                        to="erasmus.erasmusactivityinstance",
                        verbose_name="instance",
                    ),
                ),
                (
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activity_instance_registrations",
                        to="erasmus.erasmuslead",
                        verbose_name="lead",
                    ),
                ),
            ],
            options={
                "verbose_name": "Erasmus activity instance registration",
                "verbose_name_plural": "Erasmus activity instance registrations",
                "unique_together": {("lead", "instance")},
            },
        ),
    ]
