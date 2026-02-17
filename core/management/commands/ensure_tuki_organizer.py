"""
Asegura que exista el organizador Tuki (experiencias gestionadas por superadmin).
Opcional: lista organizadores con módulo de experiencias.
"""

from django.core.management.base import BaseCommand

from core.carga_helpers import get_or_create_tuki_organizer


class Command(BaseCommand):
    help = "Crea el organizador Tuki si no existe (para experiencias de operadores sin cuenta). Opción --list para listar organizadores con experiencias."

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            action="store_true",
            help="Listar organizadores con has_experience_module=True (nombre, slug, id).",
        )

    def handle(self, *args, **options):
        if options["list"]:
            from apps.organizers.models import Organizer

            orgs = Organizer.objects.filter(has_experience_module=True).order_by("name")
            self.stdout.write("Organizadores con módulo experiencias:")
            for o in orgs:
                self.stdout.write(f"  {o.name}  slug={o.slug}  id={o.id}")
            return

        org = get_or_create_tuki_organizer()
        self.stdout.write(self.style.SUCCESS(f"Organizador Tuki listo: slug={org.slug} id={org.id}"))
