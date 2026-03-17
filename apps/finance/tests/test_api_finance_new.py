"""Tests para nuevos endpoints de finance (external revenue, settlements, vendors, ledger, reports)."""

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.models import (
    ExternalRevenueRecord,
    LedgerAccount,
    SettlementRun,
    Vendor,
    VendorBill,
)

from .test_fixtures import FinanceFixturesMixin

BASE = '/api/v1/superadmin/finance'


class FinanceNewEndpointsTests(FinanceFixturesMixin, APITestCase):
    def setUp(self):
        self.create_superuser()
        self.client.force_authenticate(user=self.superuser)
        self.create_organizer()
        self.create_ledger_accounts()

    def test_finance_sync_returns_counts(self):
        response = self.client.post(f'{BASE}/sync/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('organizer_lines_synced', response.data)
        self.assertIn('external_revenue_lines_synced', response.data)

    def test_finance_overview_no_side_effects(self):
        response = self.client.get(f'{BASE}/overview/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('overview', response.data)
        self.assertIn('payees_count', response.data['overview'])

    def test_external_revenue_import(self):
        payload = {
            'records': [
                {
                    'source_type': 'manual',
                    'external_reference': 'API-EXT-001',
                    'organizer_id': str(self.organizer.id),
                    'gross_amount': 80000,
                    'platform_fee_amount': 4000,
                    'payable_amount': 76000,
                    'effective_date': '2026-03-10',
                    'currency': 'CLP',
                },
            ],
            'source': 'api_test',
        }
        response = self.client.post(f'{BASE}/external-revenue/import/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertGreaterEqual(response.data.get('records_created', 0), 1)
        self.assertTrue(ExternalRevenueRecord.objects.filter(external_reference='API-EXT-001').exists())

    def test_external_revenue_list(self):
        response = self.client.get(f'{BASE}/external-revenue/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

    def test_revenue_insights(self):
        response = self.client.get(f'{BASE}/revenue-insights/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('platform_orders', response.data)
        self.assertIn('external_revenue', response.data)

    def test_settlements_calculate(self):
        payload = {
            'scope_type': 'organizer',
            'scope_id': str(self.organizer.id),
            'organizer_id': str(self.organizer.id),
            'period_start': '2026-03-01',
            'period_end': '2026-03-31',
        }
        response = self.client.post(f'{BASE}/settlements/calculate/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertIn('settlement', response.data)

    def test_third_party_funds(self):
        response = self.client.get(f'{BASE}/third-party-funds/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('positions', response.data)

    def test_vendors_list_and_create(self):
        response = self.client.get(f'{BASE}/vendors/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_before = len(response.data.get('results', []))

        create_resp = self.client.post(
            f'{BASE}/vendors/',
            {'name': 'Proveedor API Test', 'country_code': 'CL', 'currency': 'CLP'},
            format='json',
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Vendor.objects.filter(name='Proveedor API Test').count(), 1)

    def test_vendor_aging(self):
        response = self.client.get(f'{BASE}/vendor-aging/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

    def test_expense_categories(self):
        response = self.client.get(f'{BASE}/expense-categories/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cost_centers(self):
        response = self.client.get(f'{BASE}/cost-centers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_tax_treatments(self):
        response = self.client.get(f'{BASE}/tax-treatments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_bank_accounts(self):
        response = self.client.get(f'{BASE}/bank-accounts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_treasury_position(self):
        response = self.client.get(f'{BASE}/treasury-position/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('as_of', response.data)
        self.assertIn('bank_cash_actual', response.data)

    def test_ledger_accounts(self):
        response = self.client.get(f'{BASE}/ledger/accounts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertGreater(len(response.data['results']), 0)

    def test_ledger_journal(self):
        response = self.client.get(f'{BASE}/ledger/journal/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

    def test_report_balance_sheet(self):
        response = self.client.get(f'{BASE}/reports/balance-sheet/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_assets', response.data)

    def test_report_income_statement(self):
        response = self.client.get(f'{BASE}/reports/income-statement/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_revenue', response.data)

    def test_report_cash_flow(self):
        response = self.client.get(f'{BASE}/reports/cash-flow/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('net_cash_flow', response.data)
