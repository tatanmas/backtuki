# Contest / Sorteo: Contest, ContestSlideConfig, ContestExtraField, ContestRegistration, ContestParticipationCode

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0055_erasmusactivityinscriptionpayment_exclude_from_revenue"),
        ("experiences", "0001_initial"),
        ("media", "0001_initial"),
        ("core", "0001_add_platform_flow_monitoring"),
    ]

    operations = [
        migrations.CreateModel(
            name="Contest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("slug", models.SlugField(help_text="URL identifier, e.g. salar-uyuni-2026", max_length=120, unique=True, verbose_name="slug")),
                ("title", models.CharField(max_length=255, verbose_name="title")),
                ("subtitle", models.CharField(blank=True, max_length=255, verbose_name="subtitle")),
                ("headline", models.TextField(blank=True, help_text="Main message e.g. 'Tuki y House and Flats te regalan un viaje para dos...'", verbose_name="headline")),
                ("terms_and_conditions_html", models.TextField(blank=True, help_text="Rich text (HTML) for T&C page", verbose_name="terms and conditions HTML")),
                ("requirements_html", models.TextField(blank=True, help_text="Requisitos / pasos a seguir (rich text), shown on landing", verbose_name="requirements HTML")),
                (
                    "whatsapp_confirmation_message",
                    models.TextField(
                        blank=True,
                        help_text="Message sent back when participant sends their code via WhatsApp. Placeholders: {{nombre}}, {{codigo}}, {{concurso}}.",
                        verbose_name="WhatsApp confirmation message",
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
                ("starts_at", models.DateTimeField(blank=True, null=True, verbose_name="starts at")),
                ("ends_at", models.DateTimeField(blank=True, null=True, verbose_name="ends at")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="order")),
                (
                    "experience",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contests",
                        to="experiences.experience",
                        verbose_name="experience",
                    ),
                ),
            ],
            options={
                "verbose_name": "Contest",
                "verbose_name_plural": "Contests",
                "ordering": ["order", "slug"],
            },
        ),
        migrations.CreateModel(
            name="ContestSlideConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="order")),
                ("caption", models.CharField(blank=True, max_length=255, verbose_name="caption")),
                (
                    "asset",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contest_slide_configs",
                        to="media.mediaasset",
                        verbose_name="asset",
                    ),
                ),
                (
                    "contest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="slide_configs",
                        to="erasmus.contest",
                        verbose_name="contest",
                    ),
                ),
            ],
            options={
                "verbose_name": "Contest slide config",
                "verbose_name_plural": "Contest slide configs",
                "ordering": ["contest", "order", "id"],
            },
        ),
        migrations.CreateModel(
            name="ContestExtraField",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=255, verbose_name="label")),
                ("field_key", models.SlugField(max_length=80, verbose_name="field key")),
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
                    "contest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extra_fields",
                        to="erasmus.contest",
                        verbose_name="contest",
                    ),
                ),
            ],
            options={
                "verbose_name": "Contest extra field",
                "verbose_name_plural": "Contest extra fields",
                "ordering": ["contest", "order", "id"],
                "unique_together": {("contest", "field_key")},
            },
        ),
        migrations.CreateModel(
            name="ContestRegistration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("first_name", models.CharField(max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(max_length=150, verbose_name="last name")),
                ("email", models.EmailField(blank=True, max_length=254, null=True, verbose_name="email")),
                ("phone_country_code", models.CharField(blank=True, max_length=10, verbose_name="phone country code")),
                ("phone_number", models.CharField(blank=True, max_length=20, verbose_name="phone number")),
                (
                    "extra_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Answers to ContestExtraField questions",
                        verbose_name="extra data",
                    ),
                ),
                ("accept_terms", models.BooleanField(default=False, verbose_name="accept terms")),
                (
                    "contest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registrations",
                        to="erasmus.contest",
                        verbose_name="contest",
                    ),
                ),
                (
                    "flow",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contest_registrations",
                        to="core.platformflow",
                        verbose_name="flow",
                    ),
                ),
            ],
            options={
                "verbose_name": "Contest registration",
                "verbose_name_plural": "Contest registrations",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="contestregistration",
            index=models.Index(fields=["contest", "created_at"], name="erasmus_con_contest_5a0f0d_idx"),
        ),
        migrations.CreateModel(
            name="ContestParticipationCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                ("code", models.CharField(db_index=True, max_length=50, unique=True, verbose_name="code")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pendiente"), ("confirmed", "Confirmado")],
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                (
                    "contest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participation_codes",
                        to="erasmus.contest",
                        verbose_name="contest",
                    ),
                ),
                (
                    "flow",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contest_participation_codes",
                        to="core.platformflow",
                        verbose_name="flow",
                    ),
                ),
                (
                    "registration",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participation_code",
                        to="erasmus.contestregistration",
                        verbose_name="registration",
                    ),
                ),
            ],
            options={
                "verbose_name": "Contest participation code",
                "verbose_name_plural": "Contest participation codes",
                "ordering": ["-created_at"],
            },
        ),
    ]
