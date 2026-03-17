"""
Genera public_code para todos los alojamientos que no lo tienen (creados antes de la feature).
Orden: por created_at; asigna display_order secuencial si falta y genera public_code.
Uso: python manage.py backfill_accommodation_public_codes [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accommodations.models import Accommodation
from apps.accommodations.public_code_service import generate_public_code, get_next_display_order


class Command(BaseCommand):
    help = "Genera public_code (y display_order si falta) para alojamientos que no lo tienen"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo mostrar qué se haría, sin guardar",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: no se guardará nada"))

        from django.db.models import Q
        qs = (
            Accommodation.objects.filter(deleted_at__isnull=True)
            .filter(Q(public_code__isnull=True) | Q(public_code=""))
            .order_by("created_at", "id")
        )

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Todos los alojamientos ya tienen public_code."))
            return

        self.stdout.write(f"Alojamientos sin public_code: {total}")

        next_order = get_next_display_order()
        updated = 0
        with transaction.atomic():
            for acc in qs:
                if acc.display_order is None or acc.display_order < 1:
                    acc.display_order = next_order
                    next_order += 1
                prefix = (acc.public_code_prefix or "").strip() or None
                acc.public_code = generate_public_code(acc.display_order, prefix=prefix)
                if not dry_run:
                    acc.save(update_fields=["display_order", "public_code"])
                updated += 1
                self.stdout.write(f"  {acc.id}: {acc.public_code} (orden {acc.display_order})")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN: se habría actualizado {updated} alojamiento(s)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Actualizados {updated} alojamiento(s)."))
