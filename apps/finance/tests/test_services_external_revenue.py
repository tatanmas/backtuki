"""Tests para services_external_revenue."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.finance.models import ExternalRevenueRecord, PayableLine
from apps.finance.services_external_revenue import (
    import_external_revenue,
    reverse_external_revenue_record,
    sync_external_revenue_payables,
)

from .test_fixtures import FinanceFixturesMixin


class ExternalRevenueServiceTests(FinanceFixturesMixin, TestCase):
    def setUp(self):
        self.create_organizer()

    def test_import_external_revenue_dry_run(self):
        payload = [
            {
                'source_type': 'manual',
                'external_reference': 'EXT-TEST-001',
                'organizer_id': str(self.organizer.id),
                'gross_amount': 100000,
                'platform_fee_amount': 5000,
                'payable_amount': 95000,
                'effective_date': '2026-03-01',
                'currency': 'CLP',
            },
        ]
        result = import_external_revenue(
            payload=payload,
            source='test',
            dry_run=True,
            skip_duplicates=True,
        )
        self.assertEqual(result['status'], 'dry_run')
        self.assertEqual(result['records_created'], 1)
        self.assertEqual(ExternalRevenueRecord.objects.count(), 0)

    def test_import_external_revenue_creates_records(self):
        payload = [
            {
                'source_type': 'manual',
                'external_reference': 'EXT-TEST-002',
                'organizer_id': str(self.organizer.id),
                'gross_amount': 100000,
                'platform_fee_amount': 5000,
                'payable_amount': 95000,
                'effective_date': '2026-03-01',
                'currency': 'CLP',
            },
        ]
        result = import_external_revenue(
            payload=payload,
            source='test',
            dry_run=False,
            skip_duplicates=True,
        )
        self.assertEqual(result['records_created'], 1)
        self.assertEqual(ExternalRevenueRecord.objects.count(), 1)
        record = ExternalRevenueRecord.objects.get(external_reference='EXT-TEST-002')
        self.assertEqual(record.gross_amount, Decimal('100000'))
        self.assertEqual(record.payable_amount, Decimal('95000'))

    def test_import_orphan_record_no_organizer(self):
        """Orphan records (no organizer) are allowed for pre-platform revenue."""
        payload = [
            {
                'source_type': 'manual',
                'external_reference': 'EXT-ORPHAN-001',
                'gross_amount': 50000,
                'platform_fee_amount': 2500,
                'payable_amount': 47500,
                'effective_date': '2026-03-01',
                'already_paid': True,
            },
        ]
        result = import_external_revenue(
            payload=payload,
            source='test',
            dry_run=False,
            skip_duplicates=True,
        )
        self.assertEqual(result['records_created'], 1)
        record = ExternalRevenueRecord.objects.get(external_reference='EXT-ORPHAN-001')
        self.assertIsNone(record.organizer_id)
        self.assertTrue(record.already_paid)

    def test_import_skip_duplicates(self):
        payload = [
            {
                'source_type': 'manual',
                'external_reference': 'EXT-DUP',
                'organizer_id': str(self.organizer.id),
                'gross_amount': 50000,
                'effective_date': '2026-03-01',
            },
        ]
        import_external_revenue(payload=payload, source='test', dry_run=False)
        result2 = import_external_revenue(payload=payload, source='test', dry_run=False, skip_duplicates=True)
        self.assertEqual(result2['records_skipped'], 1)
        self.assertEqual(ExternalRevenueRecord.objects.filter(external_reference='EXT-DUP').count(), 1)

    def test_reverse_external_revenue_record(self):
        record = ExternalRevenueRecord.objects.create(
            source_type='manual',
            external_reference='EXT-REV',
            organizer=self.organizer,
            gross_amount=Decimal('50000'),
            platform_fee_amount=Decimal('2500'),
            payable_amount=Decimal('47500'),
            effective_date=date(2026, 3, 1),
            status='active',
        )
        reversal = reverse_external_revenue_record(record)
        self.assertIsNotNone(reversal)
        record.refresh_from_db()
        self.assertEqual(record.status, 'reversed')
        self.assertEqual(reversal.gross_amount, Decimal('-50000'))

    def test_sync_creates_open_line_when_not_already_paid(self):
        """Sync creates PayableLine with status=open when already_paid=False."""
        self.create_payee()
        record = ExternalRevenueRecord.objects.create(
            source_type='manual',
            external_reference='EXT-SYNC-OPEN',
            organizer=self.organizer,
            gross_amount=Decimal('100000'),
            platform_fee_amount=Decimal('5000'),
            payable_amount=Decimal('95000'),
            effective_date=date(2026, 3, 1),
            status='active',
            already_paid=False,
        )
        count = sync_external_revenue_payables()
        self.assertGreaterEqual(count, 1)
        line = PayableLine.objects.get(external_revenue_record=record)
        self.assertEqual(line.status, 'open')
        self.assertIsNone(line.paid_at)

    def test_sync_creates_paid_line_when_already_paid(self):
        """Sync creates PayableLine with status=paid when already_paid=True."""
        self.create_payee()
        record = ExternalRevenueRecord.objects.create(
            source_type='manual',
            external_reference='EXT-SYNC-PAID',
            organizer=self.organizer,
            gross_amount=Decimal('80000'),
            platform_fee_amount=Decimal('4000'),
            payable_amount=Decimal('76000'),
            effective_date=date(2026, 3, 10),
            status='active',
            already_paid=True,
        )
        count = sync_external_revenue_payables()
        self.assertGreaterEqual(count, 1)
        line = PayableLine.objects.get(external_revenue_record=record)
        self.assertEqual(line.status, 'paid')
        self.assertIsNotNone(line.paid_at)

    def test_sync_skips_orphan_records(self):
        """Sync does not create PayableLine for records without organizer."""
        record = ExternalRevenueRecord.objects.create(
            source_type='manual',
            external_reference='EXT-ORPHAN-SYNC',
            organizer=None,
            gross_amount=Decimal('50000'),
            platform_fee_amount=Decimal('2500'),
            payable_amount=Decimal('47500'),
            effective_date=date(2026, 3, 1),
            status='active',
        )
        count = sync_external_revenue_payables()
        self.assertEqual(count, 0)
        self.assertFalse(PayableLine.objects.filter(external_revenue_record=record).exists())
