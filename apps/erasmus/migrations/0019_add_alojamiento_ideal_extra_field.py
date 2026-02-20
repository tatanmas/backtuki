# Data migration: add "Alojamiento ideal" as multiselect extra field

from django.db import migrations


def create_alojamiento_ideal_field(apps, schema_editor):
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


def remove_alojamiento_ideal_field(apps, schema_editor):
    ErasmusExtraField = apps.get_model("erasmus", "ErasmusExtraField")
    ErasmusExtraField.objects.filter(field_key="alojamiento_ideal").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0018_community_visibility_flags"),
    ]

    operations = [
        migrations.RunPython(create_alojamiento_ideal_field, remove_alojamiento_ideal_field),
    ]
