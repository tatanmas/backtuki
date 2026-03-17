"""Tests para services_settlements."""

from datetime import date, timedelta

from django.test import TestCase

from apps.finance.models import ExternalRevenueRecord, PayableLine, SettlementRun
from apps.finance.services_settlements import (
    calculate_settlement,
    get_partner_custody_position,
    post_settlement,
    void_settlement,
)

from .test_fixtures import FinanceFixturesMixin


class SettlementsServiceTests(FinanceFixturesMixin, TestCase):
    def setUp(self):
        self.create_organizer()
        self.create_event_and_order()
        self.create_payee()

    def test_calculate_settlement_event_scope(self):
        period_start = date.today() - timedelta(days=1)
        period_end = date.today() + timedelta(days=1)
        settlement = calculate_settlement(
            scope_type='event',
            scope_id=str(self.event.id),
            organizer=self.organizer,
            period_start=period_start,
            period_end=period_end,
        )
        self.assertIsNotNone(settlement)
        self.assertEqual(settlement.status, 'calculated')
        self.assertEqual(settlement.scope_type, 'event')
        self.assertGreaterEqual(settlement.lines.count(), 0)

    def test_calculate_settlement_organizer_scope_with_ext_revenue(self):
        ExternalRevenueRecord.objects.create(
            source_type='manual',
            external_reference='EXT-SET-001',
            organizer=self.organizer,
            gross_amount=50000,
            platform_fee_amount=2500,
            payable_amount=47500,
            effective_date=date.today(),
            status='active',
            currency='CLP',
        )
        period_start = date.today() - timedelta(days=1)
        period_end = date.today() + timedelta(days=1)
        settlement = calculate_settlement(
            scope_type='organizer',
            scope_id=str(self.organizer.id),
            organizer=self.organizer,
            period_start=period_start,
            period_end=period_end,
        )
        self.assertIsNotNone(settlement)
        self.assertEqual(settlement.status, 'calculated')
        self.assertGreaterEqual(settlement.lines.count(), 1)
        self.assertGreaterEqual(settlement.payable_amount, 47500)

    def test_post_settlement_creates_payables(self):
        ExternalRevenueRecord.objects.create(
            source_type='manual',
            external_reference='EXT-POST-001',
            organizer=self.organizer,
            gross_amount=30000,
            platform_fee_amount=1500,
            payable_amount=28500,
            effective_date=date.today(),
            status='active',
            currency='CLP',
        )
        settlement = calculate_settlement(
            scope_type='organizer',
            scope_id=str(self.organizer.id),
            organizer=self.organizer,
            period_start=date.today() - timedelta(days=1),
            period_end=date.today() + timedelta(days=1),
        )
        post_settlement(settlement)
        settlement.refresh_from_db()
        self.assertEqual(settlement.status, 'posted')
        self.assertGreater(PayableLine.objects.filter(settlement_run=settlement).count(), 0)

    def test_void_settlement_draft(self):
        settlement = calculate_settlement(
            scope_type='organizer',
            scope_id=str(self.organizer.id),
            organizer=self.organizer,
            period_start=date.today(),
            period_end=date.today(),
        )
        void_settlement(settlement)
        settlement.refresh_from_db()
        self.assertEqual(settlement.status, 'voided')

    def test_get_partner_custody_position(self):
        pos = get_partner_custody_position(self.organizer)
        self.assertIn('organizer_id', pos)
        self.assertIn('gross_collected', pos)
        self.assertIn('payable_total', pos)
        self.assertIn('retained', pos)
