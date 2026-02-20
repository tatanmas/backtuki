# Data migration: add "Deportes" as open text (textarea) in interests context

from django.db import migrations


def create_deportes_field(apps, schema_editor):
    ErasmusExtraField = apps.get_model("erasmus", "ErasmusExtraField")
    if ErasmusExtraField.objects.filter(field_key="deportes").exists():
        return
    ErasmusExtraField.objects.create(
        label="¿Qué deportes practicas? (escribir libremente)",
        field_key="deportes",
        type="textarea",
        required=False,
        placeholder="Ej: fútbol, surf, trekking, escalada...",
        order=20,
        is_active=True,
    )


def remove_deportes_field(apps, schema_editor):
    ErasmusExtraField = apps.get_model("erasmus", "ErasmusExtraField")
    ErasmusExtraField.objects.filter(field_key="deportes").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0026_erasmuslead_form_locale"),
    ]

    operations = [
        migrations.RunPython(create_deportes_field, remove_deportes_field),
    ]
