"""
Borra alojamientos por slug, sus reseñas y todas las fotos (MediaAsset) asociadas.
Para ejecutar en Dako cuando se quiera recrear desde cero, p. ej. tras subir fotos incorrectas.
Uso: python manage.py carga_borrar_alojamientos rocas-de-elki rocas-de-elki-terral
"""

from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from apps.accommodations.models import Accommodation
from apps.media.models import MediaAsset
from apps.landing_destinations.models import LandingDestination


def _ids_from_gallery(gallery_media_ids):
    """Convierte gallery_media_ids (list de str/int) a lista de int para consulta."""
    if not gallery_media_ids:
        return []
    out = []
    for x in gallery_media_ids:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return out


class Command(BaseCommand):
    help = "Borra alojamientos por slug, sus reseñas y las fotos (MediaAsset) asociadas."

    def add_arguments(self, parser):
        parser.add_argument(
            "slugs",
            nargs="+",
            type=str,
            help="Slugs de alojamientos a borrar (ej. rocas-de-elki rocas-de-elki-terral).",
        )

    def handle(self, *args, **options):
        slugs = [s.strip() for s in options["slugs"] if s.strip()]
        if not slugs:
            self.stderr.write(self.style.ERROR("Indica al menos un slug."))
            return

        deleted_acc = 0
        deleted_media = 0
        for slug in slugs:
            acc = Accommodation.objects.filter(slug=slug).first()
            if not acc:
                self.stdout.write(self.style.WARNING(f"No existe: {slug}"))
                continue

            title = acc.title
            media_ids = _ids_from_gallery(acc.gallery_media_ids or [])
            # Borrar fotos (archivo en storage + registro MediaAsset)
            for asset in MediaAsset.objects.filter(id__in=media_ids):
                if asset.file:
                    try:
                        default_storage.delete(asset.file.name)
                        self.stdout.write(f"  Archivo borrado: {asset.file.name}")
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"  No se pudo borrar archivo {asset.file.name}: {e}"))
                asset.delete()
                deleted_media += 1
            if media_ids:
                self.stdout.write(self.style.SUCCESS(f"  {len(media_ids)} foto(s) borrada(s) para {slug}"))

            acc_id_str = str(acc.id)
            # Quitar de accommodation_ids de destinos (ej. Valle de Elqui)
            for dest in LandingDestination.objects.exclude(accommodation_ids=[]):
                ids = list(dest.accommodation_ids or [])
                if acc_id_str in ids:
                    ids.remove(acc_id_str)
                    dest.accommodation_ids = ids
                    dest.save(update_fields=["accommodation_ids"])
                    self.stdout.write(f"  Quitado de destino: {dest.slug}")

            acc.delete()
            self.stdout.write(self.style.SUCCESS(f"Borrado alojamiento: {slug} ({title})"))
            deleted_acc += 1

        if deleted_acc:
            self.stdout.write(self.style.SUCCESS(f"Total: {deleted_acc} alojamiento(s), {deleted_media} foto(s)."))
