"""Seed the default chart of accounts for the Tuki financial ledger."""

from django.core.management.base import BaseCommand

from apps.finance.models import LedgerAccount


DEFAULT_ACCOUNTS = [
    # Assets
    {'code': '1.1.01', 'name': 'Caja', 'account_type': 'asset', 'subtype': 'cash'},
    {'code': '1.1.02', 'name': 'Bancos', 'account_type': 'asset', 'subtype': 'bank'},
    {'code': '1.1.03', 'name': 'Processor clearing en tránsito', 'account_type': 'asset', 'subtype': 'processor_clearing'},
    {'code': '1.1.04', 'name': 'Cuentas por cobrar – partners', 'account_type': 'asset', 'subtype': 'receivable'},
    {'code': '1.1.05', 'name': 'IVA crédito fiscal', 'account_type': 'asset', 'subtype': 'tax_credit'},
    {'code': '1.1.06', 'name': 'Cuentas por cobrar – organizers (recovery)', 'account_type': 'asset', 'subtype': 'receivable'},

    # Liabilities
    {'code': '2.1.10', 'name': 'Fondos de terceros por liquidar', 'account_type': 'liability', 'subtype': 'third_party_funds'},
    {'code': '2.1.11', 'name': 'Cuentas por pagar – partners', 'account_type': 'liability', 'subtype': 'payable_partners'},
    {'code': '2.1.20', 'name': 'Cuentas por pagar – proveedores', 'account_type': 'liability', 'subtype': 'payable_vendors'},
    {'code': '2.1.30', 'name': 'Pasivo con related parties', 'account_type': 'liability', 'subtype': 'related_party'},

    # Equity
    {'code': '3.1.01', 'name': 'Capital aportado', 'account_type': 'equity', 'subtype': 'capital'},
    {'code': '3.1.02', 'name': 'Resultados acumulados', 'account_type': 'equity', 'subtype': 'retained_earnings'},

    # Revenue
    {'code': '4.1.01', 'name': 'Ingresos por comisión', 'account_type': 'revenue', 'subtype': 'commission'},
    {'code': '4.1.02', 'name': 'Ingresos por service fee', 'account_type': 'revenue', 'subtype': 'service_fee'},

    # Expenses
    {'code': '5.1.01', 'name': 'Gastos operativos generales', 'account_type': 'expense', 'subtype': 'general'},
    {'code': '5.1.02', 'name': 'Gasto procesador de pagos', 'account_type': 'expense', 'subtype': 'processor_fees'},
    {'code': '5.1.03', 'name': 'Gastos servicios exterior', 'account_type': 'expense', 'subtype': 'foreign_services'},
    {'code': '5.1.04', 'name': 'Pérdida por processor fee no recuperable', 'account_type': 'expense', 'subtype': 'processor_fee_loss'},
]


class Command(BaseCommand):
    help = 'Seed the default chart of accounts for the financial ledger'

    def handle(self, *args, **options):
        created = 0
        for acct in DEFAULT_ACCOUNTS:
            _, was_created = LedgerAccount.objects.get_or_create(
                code=acct['code'],
                defaults={
                    'name': acct['name'],
                    'account_type': acct['account_type'],
                    'subtype': acct['subtype'],
                },
            )
            if was_created:
                created += 1
                self.stdout.write(f'  Created: {acct["code"]} – {acct["name"]}')

        self.stdout.write(self.style.SUCCESS(f'Done. {created} accounts created.'))
