"""
Seed finanzas con datos de demo para ver el panel funcionando.

Crea: cuentas bancarias con saldos, revenue externo con organizador,
proveedores, y sincroniza payables. Para que los summary cards muestren
montos reales en vez de $0.

Uso:
  python manage.py seed_finance_demo
  python manage.py seed_finance_demo --reset  # borra datos demo previos
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.finance.models import (
    BankAccount,
    BankBalanceSnapshot,
    ExternalRevenueRecord,
    Vendor,
)
from apps.finance.services import set_next_payment_dates, sync_all_payables
from apps.finance.services_external_revenue import sync_external_revenue_payables


DEMO_BANK_NAME = "Cuenta Principal Demo"
DEMO_ORG_SLUG = "tuki"  # Organizador Tuki existente


class Command(BaseCommand):
    help = "Seed finance demo data: bank accounts, external revenue, vendors, sync payables"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Eliminar datos demo previos antes de crear nuevos",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self._reset_demo()

        organizer = self._get_organizer()
        if not organizer:
            self.stdout.write(self.style.WARNING("No hay organizador. Ejecuta: python manage.py ensure_tuki_organizer"))
            return

        self.stdout.write(f"Usando organizador: {organizer.name} (id={organizer.id})")

        # 1. Cuenta bancaria + snapshot
        acc, created = BankAccount.objects.get_or_create(
            name=DEMO_BANK_NAME,
            defaults={
                "bank_name": "Banco Demo",
                "account_number_masked": "****1234",
                "currency": "CLP",
                "country_code": "CL",
            },
        )
        if created:
            self.stdout.write(f"  Cuenta bancaria creada: {acc.name}")

        today = date.today()
        BankBalanceSnapshot.objects.update_or_create(
            bank_account=acc,
            snapshot_date=today,
            defaults={"balance": Decimal("5000000"), "source": "seed_demo"},
        )
        self.stdout.write(f"  Snapshot banco: $5.000.000 al {today}")

        # 2. Revenue externo con organizador (para que cree PayableLines)
        refs = [
            ("DEMO-2024-01", "Tour Torres del Paine", 450000),
            ("DEMO-2024-02", "Experiencia Valle del Elqui", 280000),
            ("DEMO-2024-03", "Alojamiento Valle Nevado", 320000),
            ("DEMO-2025-01", "Free Tour Santiago Centro", 150000),
            ("DEMO-2025-02", "Tour Viña del Mar", 220000),
        ]
        for ref, label, gross in refs:
            year = 2024 if "2024" in ref else 2025
            eff_date = date(year, 6, 15)
            fee = int(gross * 0.15)
            pay = gross - fee
            _, created = ExternalRevenueRecord.objects.get_or_create(
                source_type="demo",
                external_reference=ref,
                defaults={
                    "organizer": organizer,
                    "product_label": label,
                    "gross_amount": gross,
                    "platform_fee_amount": fee,
                    "payable_amount": pay,
                    "currency": "CLP",
                    "effective_date": eff_date,
                    "already_paid": True,
                    "status": "active",
                    "commercial_mode": "collect_total",
                },
            )
            if created:
                self.stdout.write(f"  Revenue externo: {ref} {label} ${gross:,}")

        # 3. Proveedor
        vendor, created = Vendor.objects.get_or_create(
            name="Proveedor Demo SPA",
            defaults={
                "legal_name": "Proveedor Demo SpA",
                "tax_id": "76123456-7",
                "country_code": "CL",
                "currency": "CLP",
                "email": "demo@proveedor.cl",
                "status": "active",
            },
        )
        if created:
            self.stdout.write(f"  Proveedor creado: {vendor.name}")

        # 4. Sincronizar payables (external revenue -> PayableLine)
        count = sync_external_revenue_payables()
        self.stdout.write(f"  Sync revenue externo -> payables: {count} líneas")

        # 5. Sync general y fechas
        sync_all_payables()
        set_next_payment_dates()
        self.stdout.write("  Sync payables y fechas ejecutado")

        self.stdout.write(self.style.SUCCESS("Done. Refresca Finanzas para ver los datos."))

    def _get_organizer(self):
        from apps.organizers.models import Organizer

        org = Organizer.objects.filter(slug=DEMO_ORG_SLUG).first()
        if org:
            return org
        return Organizer.objects.filter(has_experience_module=True).first()

    def _reset_demo(self):
        # Solo borrar lo que creamos (evitar borrar datos reales)
        for acc in list(BankAccount.objects.filter(name=DEMO_BANK_NAME)):
            BankBalanceSnapshot.objects.filter(bank_account=acc).delete()
            acc.delete()
        ExternalRevenueRecord.objects.filter(source_type="demo").delete()
        Vendor.objects.filter(name="Proveedor Demo SPA").delete()
        self.stdout.write("  Reset: datos demo eliminados")
