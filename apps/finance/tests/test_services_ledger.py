"""Tests para services_ledger – posting engine doble partida."""

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.finance.models import JournalEntry, JournalLine, LedgerAccount
from apps.finance.services_ledger import (
    create_journal_entry,
    reverse_journal_entry,
)

from .test_fixtures import FinanceFixturesMixin


class LedgerServiceTests(FinanceFixturesMixin, TestCase):
    def setUp(self):
        self.create_ledger_accounts()

    def test_create_journal_entry_balanced(self):
        sid = uuid.uuid4()
        entry = create_journal_entry(
            source_type='test',
            source_id=str(sid),
            posting_event='test_posting',
            lines=[
                {'account_code': '1.1.02', 'debit': 1000, 'credit': 0},
                {'account_code': '2.1.10', 'debit': 0, 'credit': 1000},
            ],
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.status, 'posted')
        self.assertTrue(entry.is_balanced)
        self.assertEqual(entry.lines.count(), 2)

    def test_create_journal_entry_idempotent(self):
        sid = uuid.uuid4()
        lines = [
            {'account_code': '1.1.02', 'debit': 500, 'credit': 0},
            {'account_code': '2.1.10', 'debit': 0, 'credit': 500},
        ]
        e1 = create_journal_entry(
            source_type='test',
            source_id=str(sid),
            posting_event='idem_test',
            lines=lines,
        )
        e2 = create_journal_entry(
            source_type='test',
            source_id=str(sid),
            posting_event='idem_test',
            lines=lines,
        )
        self.assertIsNotNone(e1)
        self.assertIsNone(e2)
        self.assertEqual(JournalEntry.objects.filter(idempotency_key=f'test:{sid}:idem_test').count(), 1)

    def test_create_journal_entry_unbalanced_raises(self):
        with self.assertRaises(ValueError) as ctx:
            create_journal_entry(
                source_type='test',
                source_id=str(uuid.uuid4()),
                posting_event='unbal',
                lines=[
                    {'account_code': '1.1.02', 'debit': 1000, 'credit': 0},
                    {'account_code': '2.1.10', 'debit': 0, 'credit': 500},
                ],
            )
        self.assertIn('not balanced', str(ctx.exception))

    def test_reverse_journal_entry(self):
        sid = uuid.uuid4()
        entry = create_journal_entry(
            source_type='test',
            source_id=str(sid),
            posting_event='rev_test',
            lines=[
                {'account_code': '1.1.02', 'debit': 2000, 'credit': 0},
                {'account_code': '2.1.10', 'debit': 0, 'credit': 2000},
            ],
        )
        reversal = reverse_journal_entry(entry, description='Reversal test')
        self.assertIsNotNone(reversal)
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'reversed')
        self.assertEqual(reversal.reversal_of_id, entry.id)
        for line in reversal.lines.all():
            self.assertEqual(line.debit_amount + line.credit_amount, 2000)
