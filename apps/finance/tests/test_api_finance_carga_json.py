"""
Tests para APIs de carga JSON: cartolas, facturas, revenue externo, schema.
Cubre todos los casos base para validar que el backend funciona correctamente.
"""

from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.models import (
    BankAccount,
    BankStatementLine,
    ExternalRevenueRecord,
    ExpenseCategory,
    TaxTreatment,
    Vendor,
    VendorBill,
)

from .test_fixtures import FinanceFixturesMixin

BASE = '/api/v1/superadmin/finance'
SCHEMA_BASE = '/api/v1/superadmin/schema'


class BankStatementsImportTests(FinanceFixturesMixin, APITestCase):
    """Tests para importación de cartolas bancarias."""

    def setUp(self):
        self.create_superuser()
        self.client.force_authenticate(user=self.superuser)
        self.account = BankAccount.objects.create(
            name='Cuenta Test Principal',
            bank_name='Banco Test',
            account_number_masked='1234-5678',
            currency='CLP',
            country_code='CL',
        )

    def test_import_by_bank_account_id(self):
        payload = {
            'bank_account_id': str(self.account.id),
            'lines': [
                {
                    'statement_date': '2026-03-01',
                    'value_date': '2026-03-01',
                    'description': 'TRANSFERENCIA RECIBIDA',
                    'amount': 450000,
                    'balance_after': 1200000,
                },
                {
                    'statement_date': '2026-03-02',
                    'description': 'PAGO SERVICIOS',
                    'amount': -45000,
                    'balance_after': 1155000,
                },
            ],
        }
        response = self.client.post(f'{BASE}/bank-statements/import/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertEqual(response.data.get('lines_created'), 2)
        self.assertEqual(BankStatementLine.objects.filter(bank_account=self.account).count(), 2)

    def test_import_by_bank_account_name(self):
        payload = {
            'bank_account_name': 'Cuenta Test Principal',
            'lines': [
                {'statement_date': '2026-03-01', 'amount': 100000, 'description': 'Ingreso'},
            ],
        }
        response = self.client.post(f'{BASE}/bank-statements/import/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('lines_created'), 1)

    def test_import_rejects_empty_lines(self):
        payload = {'bank_account_id': str(self.account.id), 'lines': []}
        response = self.client.post(f'{BASE}/bank-statements/import/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('lines', response.data.get('message', ''))

    def test_import_rejects_missing_account(self):
        payload = {
            'lines': [{'statement_date': '2026-03-01', 'amount': 100000}],
        }
        response = self.client.post(f'{BASE}/bank-statements/import/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class VendorBillsCreateFromJsonTests(FinanceFixturesMixin, APITestCase):
    """Tests para creación bulk de facturas desde JSON."""

    def setUp(self):
        self.create_superuser()
        self.client.force_authenticate(user=self.superuser)
        self.create_organizer()
        self.vendor = Vendor.objects.create(
            name='Proveedor Existente',
            tax_id='76123456-7',
            country_code='CL',
            currency='CLP',
        )

    def test_create_bills_with_vendor_id(self):
        payload = {
            'bills': [
                {
                    'vendor_id': str(self.vendor.id),
                    'bill_number': 'F-001',
                    'issue_date': '2026-03-01',
                    'due_date': '2026-03-15',
                    'total_amount': 150000,
                    'subtotal_amount': 126050,
                    'tax_amount': 23950,
                },
            ],
        }
        response = self.client.post(f'{BASE}/vendor-bills/create-from-json/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data.get('success'))
        self.assertEqual(response.data.get('created'), 1)
        self.assertEqual(VendorBill.objects.filter(vendor=self.vendor, bill_number='F-001').count(), 1)

    def test_create_bills_with_vendor_object_creates_vendor(self):
        payload = {
            'bills': [
                {
                    'vendor': {'name': 'Nuevo Proveedor SpA', 'tax_id': '76987654-3'},
                    'bill_number': 'F-002',
                    'issue_date': '2026-03-02',
                    'due_date': '2026-03-16',
                    'total_amount': 45000,
                },
            ],
        }
        response = self.client.post(f'{BASE}/vendor-bills/create-from-json/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.get('created'), 1)
        self.assertTrue(Vendor.objects.filter(name='Nuevo Proveedor SpA').exists())
        bill = VendorBill.objects.get(bill_number='F-002')
        self.assertEqual(bill.vendor.name, 'Nuevo Proveedor SpA')

    def test_create_bills_reuses_existing_vendor_by_name(self):
        payload = {
            'bills': [
                {
                    'vendor': {'name': 'Proveedor Existente'},
                    'bill_number': 'F-003',
                    'issue_date': '2026-03-03',
                    'due_date': '2026-03-17',
                    'total_amount': 30000,
                },
            ],
        }
        response = self.client.post(f'{BASE}/vendor-bills/create-from-json/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        bill = VendorBill.objects.get(bill_number='F-003')
        self.assertEqual(bill.vendor_id, self.vendor.id)

    def test_create_bills_rejects_empty(self):
        response = self.client.post(
            f'{BASE}/vendor-bills/create-from-json/',
            {'bills': []},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ExternalRevenueImportApiTests(FinanceFixturesMixin, APITestCase):
    """Tests para API de import de revenue externo (complementa test_api_finance_new)."""

    def setUp(self):
        self.create_superuser()
        self.client.force_authenticate(user=self.superuser)
        self.create_organizer()

    def test_import_orphan_record_via_api(self):
        payload = {
            'records': [
                {
                    'external_reference': 'API-ORPHAN-001',
                    'effective_date': '2026-03-01',
                    'gross_amount': 50000,
                    'platform_fee_amount': 2500,
                    'payable_amount': 47500,
                    'product_label': 'Evento sin organizador',
                    'already_paid': True,
                },
            ],
        }
        response = self.client.post(f'{BASE}/external-revenue/import/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('records_created'), 1)
        record = ExternalRevenueRecord.objects.get(external_reference='API-ORPHAN-001')
        self.assertIsNone(record.organizer_id)
        self.assertTrue(record.already_paid)

    def test_import_with_organizer_and_already_paid(self):
        payload = {
            'records': [
                {
                    'external_reference': 'API-PAID-001',
                    'effective_date': '2026-03-10',
                    'gross_amount': 100000,
                    'platform_fee_amount': 5000,
                    'payable_amount': 95000,
                    'organizer_id': str(self.organizer.id),
                    'already_paid': True,
                },
            ],
        }
        response = self.client.post(f'{BASE}/external-revenue/import/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        record = ExternalRevenueRecord.objects.get(external_reference='API-PAID-001')
        self.assertEqual(record.organizer_id, self.organizer.id)
        self.assertTrue(record.already_paid)

    def test_external_revenue_list_includes_already_paid(self):
        ExternalRevenueRecord.objects.create(
            source_type='manual',
            external_reference='EXT-LIST-PAID',
            organizer=self.organizer,
            gross_amount=Decimal('80000'),
            platform_fee_amount=Decimal('4000'),
            payable_amount=Decimal('76000'),
            effective_date=date(2026, 3, 1),
            status='active',
            already_paid=True,
        )
        response = self.client.get(f'{BASE}/external-revenue/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', [])
        item = next((r for r in results if r['external_reference'] == 'EXT-LIST-PAID'), None)
        self.assertIsNotNone(item)
        self.assertTrue(item.get('already_paid'))


class SchemaApiTests(FinanceFixturesMixin, APITestCase):
    """Tests para API de schema (instrucciones para IA)."""

    def setUp(self):
        self.create_superuser()
        self.client.force_authenticate(user=self.superuser)

    def test_schema_bank_statement(self):
        response = self.client.get(f'{SCHEMA_BASE}/bank_statement/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('entity'), 'bank_statement')
        self.assertIn('schema', response.data)
        self.assertIn('instructions', response.data)
        self.assertIn('lines', str(response.data.get('schema', {})))

    def test_schema_vendor_bill(self):
        response = self.client.get(f'{SCHEMA_BASE}/vendor_bill/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('entity'), 'vendor_bill')
        self.assertIn('bills', str(response.data.get('schema', {})))

    def test_schema_external_revenue(self):
        response = self.client.get(f'{SCHEMA_BASE}/external_revenue/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('entity'), 'external_revenue')
        self.assertIn('records', str(response.data.get('schema', {})))
        self.assertIn('already_paid', str(response.data.get('instructions', '')))

    def test_schema_invalid_entity_returns_400(self):
        response = self.client.get(f'{SCHEMA_BASE}/invalid_entity_xyz/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
