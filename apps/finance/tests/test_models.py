"""Tests para modelos de finance."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.finance.models import (
    CommercialPolicy,
    ExternalRevenueRecord,
    LedgerAccount,
    PayableLine,
    PayeeAccount,
    SettlementRun,
    Vendor,
    VendorBill,
)
from apps.organizers.models import Organizer

from .test_fixtures import FinanceFixturesMixin


class FinanceModelsTests(FinanceFixturesMixin, TestCase):
    def setUp(self):
        self.create_organizer()
        self.create_ledger_accounts()

    def test_commercial_policy_creation(self):
        policy = self.create_commercial_policy(commercial_mode='collect_total')
        self.assertEqual(policy.commercial_mode, 'collect_total')
        self.assertEqual(policy.scope_type, 'organizer_default')
        self.assertTrue(policy.is_active)

    def test_external_revenue_record_creation(self):
        record = ExternalRevenueRecord.objects.create(
            source_type='manual',
            external_reference='EXT-001',
            organizer=self.organizer,
            gross_amount=Decimal('100000'),
            platform_fee_amount=Decimal('5000'),
            payable_amount=Decimal('95000'),
            effective_date=date.today(),
            status='active',
        )
        self.assertEqual(record.gross_amount, Decimal('100000'))
        self.assertEqual(record.status, 'active')

    def test_ledger_account_seed(self):
        acc = LedgerAccount.objects.get(code='1.1.02')
        self.assertEqual(acc.name, 'Bancos')
        self.assertEqual(acc.account_type, 'asset')

    def test_vendor_bill_creation(self):
        vendor, bill = self.create_vendor_and_bill()
        self.assertEqual(bill.total_amount, Decimal('119000'))
        self.assertEqual(bill.status, 'draft')
        self.assertEqual(bill.vendor, vendor)

    def test_settlement_run_creation(self):
        settlement = SettlementRun.objects.create(
            scope_type='event',
            scope_id=self.organizer.id,
            organizer=self.organizer,
            commercial_mode='collect_total',
            recognition_policy='on_settlement_close',
            settlement_policy='per_product',
            period_start=date.today(),
            period_end=date.today(),
            settlement_date=date.today(),
            status='draft',
        )
        self.assertEqual(settlement.status, 'draft')
        self.assertEqual(settlement.organizer, self.organizer)
