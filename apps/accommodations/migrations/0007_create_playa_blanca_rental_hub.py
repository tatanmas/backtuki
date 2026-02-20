# Data migration: create default RentalHub "playa-blanca" so the central landing works.

from django.db import migrations


def create_playa_blanca_hub(apps, schema_editor):
    RentalHub = apps.get_model("accommodations", "RentalHub")
    if not RentalHub.objects.filter(slug="playa-blanca").exists():
        RentalHub.objects.create(
            slug="playa-blanca",
            name="Arenas de Playa Blanca",
            short_description="Exclusivo condominio en Playa Blanca. Tranquilidad, conexión natural y una experiencia única en familia.",
            description="""Un proyecto ÚNICO, enfocado en cada detalle y espacios, para entregar a nuestros clientes una experiencia de vacaciones de alta calidad, valorando con un amor único nuestro entorno y su biodiversidad.

En el sector de Playa Blanca: tranquilidad, conexión natural y experiencia. Un lugar especial para disfrutar en familia.

Equipamiento del departamento:
• Terrazas con Baranda de Cristal.
• Balcones con Cierre Apilable de Cristal.
• Cocina Full Equipada.
• Piso Porcelánico en todo el Departamento.
• Ventanas Termopanel de PVC.
• Losa Radiante Eléctrica, Marcador propio.

Equipamiento del condominio:
• Piscina Temperada y Piscina al aire libre.
• Juegos para niños.
• Iluminación exterior LED con paneles fotovoltaicos.
• Sensores de movimiento.

Con eficiencia energética a través de paneles solares para espacios comunes y planta de tratamiento de agua.

Disfruta de un entorno lleno de la magia de la naturaleza, con un paisajismo único y una espectacular vista a la profundidad del océano.""",
            meta_title="Central de Arrendamiento - Arenas de Playa Blanca",
            meta_description="Reserva tu departamento en Arenas de Playa Blanca. Exclusivo condominio, conexión natural y experiencia única.",
            is_active=True,
        )


def noop_reverse(apps, schema_editor):
    # Opcional: no borramos el hub al revertir para no perder datos.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0006_rename_accommodati_accommo_6b0b0d_idx_accommodati_accommo_cf3127_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(create_playa_blanca_hub, noop_reverse),
    ]
