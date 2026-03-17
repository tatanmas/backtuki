"""Tests for bank reconciliation services."""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import (
    BankAccount,
    BankStatementLine,
    LedgerAccount,
    Payout,
    PayeeAccount,
)
from apps.finance.services_bank_reconciliation import (
    classify_statement_line,
    get_matchable_payouts,
    get_reconciliation_summary,
    ignore_statement_line,
    list_statement_lines,
    unclassify_statement_line,
)


class BankReconciliationServiceTests(TestCase):
    def setUp(self):
        self.account = BankAccount.objects.create(
            name='Cuenta Corriente',
            bank_name='Banco Test',
            currency='CLP',
        )
        self.line = BankStatementLine.objects.create(
            bank_account=self.account,
            statement_date='2026-03-01',
            description='Transferencia recibida',
            amount=Decimal('150000'),
            status='imported',
        )

    def test_list_statement_lines(self):
        lines, total = list_statement_lines(bank_account_id=self.account.id)
        self.assertEqual(total, 1)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].id, self.line.id)

    def test_list_statement_lines_filter_by_status(self):
        lines, total = list_statement_lines(
            bank_account_id=self.account.id,
            status='imported',
        )
        self.assertEqual(total, 1)
        lines, total = list_statement_lines(
            bank_account_id=self.account.id,
            status='matched',
        )
        self.assertEqual(total, 0)

    def test_classify_with_movement_type_only(self):
        line = classify_statement_line(
            line_id=self.line.id,
            movement_type='other',
            classification_note='Revisar después',
        )
        self.assertEqual(line.movement_type, 'other')
        self.assertEqual(line.classification_note, 'Revisar después')
        self.assertEqual(line.status, 'matched')

    def test_unclassify(self):
        classify_statement_line(
            line_id=self.line.id,
            movement_type='other',
        )
        line = unclassify_statement_line(self.line.id)
        self.assertEqual(line.movement_type, '')
        self.assertEqual(line.status, 'imported')
        self.assertIsNone(line.matched_payout_id)

    def test_ignore_statement_line(self):
        line = ignore_statement_line(self.line.id)
        self.assertEqual(line.status, 'ignored')

    def test_get_reconciliation_summary(self):
        summary = get_reconciliation_summary(self.account.id)
        self.assertEqual(summary['imported_count'], 1)
        self.assertEqual(summary['matched_count'], 0)
        self.assertEqual(summary['total_imported_amount'], 150000.0)

    def test_get_matchable_payouts_empty(self):
        payouts = get_matchable_payouts()
        self.assertEqual(len(payouts), 0)
