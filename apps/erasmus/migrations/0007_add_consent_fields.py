# Migration: consent fields for T&C Especiales Registro Erasmus

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0006_add_accommodation_rumi4students"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmuslead",
            name="accept_tc_erasmus",
            field=models.BooleanField(
                default=False,
                help_text="Usuario acepta T&C Especiales del Registro Erasmus",
                verbose_name="accept TC Erasmus",
            ),
        ),
        migrations.AddField(
            model_name="erasmuslead",
            name="accept_privacy_erasmus",
            field=models.BooleanField(
                default=False,
                help_text="Usuario declara haber leído Política de Privacidad y addendum Erasmus",
                verbose_name="accept privacy Erasmus",
            ),
        ),
        migrations.AddField(
            model_name="erasmuslead",
            name="consent_email",
            field=models.BooleanField(
                default=False,
                help_text="Consentimiento para recibir recomendaciones por email",
                verbose_name="consent email",
            ),
        ),
        migrations.AddField(
            model_name="erasmuslead",
            name="consent_whatsapp",
            field=models.BooleanField(
                default=False,
                help_text="Consentimiento para recibir recomendaciones por WhatsApp",
                verbose_name="consent WhatsApp",
            ),
        ),
        migrations.AddField(
            model_name="erasmuslead",
            name="consent_share_providers",
            field=models.BooleanField(
                default=False,
                help_text="Autorización para compartir datos mínimos con proveedores al solicitar cotización/reserva",
                verbose_name="consent share providers",
            ),
        ),
    ]
