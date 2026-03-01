# Data migration: remove "Alojamiento ideal" extra field (pregunta no deseada)

from django.db import migrations


def remove_alojamiento_ideal_field(apps, schema_editor):
    ErasmusExtraField = apps.get_model("erasmus", "ErasmusExtraField")
    ErasmusExtraField.objects.filter(field_key="alojamiento_ideal").delete()


def recreate_alojamiento_ideal_field(apps, schema_editor):
    """Reverse: restore the field in case of rollback."""
    ErasmusExtraField = apps.get_model("erasmus", "ErasmusExtraField")
    if ErasmusExtraField.objects.filter(field_key="alojamiento_ideal").exists():
        return
    ErasmusExtraField.objects.create(
        label="¿En qué tipo de alojamiento te sientes más cómodo al viajar?",
        field_key="alojamiento_ideal",
        type="multiselect",
        required=False,
        order=10,
        is_active=True,
        options=[
            {"value": "hotel", "label": "Hotel"},
            {"value": "hostal", "label": "Hostal"},
            {"value": "apartamento", "label": "Apartamento"},
            {"value": "habitacion_compartida", "label": "Habitación en casa compartida"},
            {"value": "casa_compartida", "label": "Casa compartida"},
            {"value": "couchsurfing", "label": "Couchsurfing"},
            {"value": "camping", "label": "Camping"},
            {"value": "otro", "label": "Otro"},
        ],
    )


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0029_alter_erasmusactivity_location"),
    ]

    operations = [
        migrations.RunPython(remove_alojamiento_ideal_field, recreate_alojamiento_ideal_field),
    ]
