"""Tests para services_reports – trial balance, balance sheet, income statement, cash flow."""

import uuid
from datetime import date

from django.test import TestCase

from apps.finance.models import JournalEntry, JournalLine, LedgerAccount
from apps.finance.services_ledger import create_journal_entry
from apps.finance.services_reports import (
    balance_sheet,
    cash_flow_basic,
    income_statement,
    trial_balance,
)

from .test_fixtures import FinanceFixturesMixin


class ReportsServiceTests(FinanceFixturesMixin, TestCase):
    def setUp(self):
        self.create_ledger_accounts()
        create_journal_entry(
            source_type='test',
            source_id=str(uuid.uuid4()),
            posting_event='test_revenue',
            lines=[
                {'account_code': '1.1.02', 'debit': 100000, 'credit': 0},
                {'account_code': '4.1.01', 'debit': 0, 'credit': 100000},
            ],
        )

    def test_trial_balance_returns_list(self):
        tb = trial_balance()
        self.assertIsInstance(tb, list)
        codes = [r['account_code'] for r in tb]
        self.assertIn('1.1.02', codes)
        self.assertIn('4.1.01', codes)

    def test_balance_sheet_structure(self):
        bs = balance_sheet()
        self.assertIn('as_of', bs)
        self.assertIn('assets', bs)
        self.assertIn('liabilities', bs)
        self.assertIn('equity', bs)
        self.assertIn('total_assets', bs)
        self.assertIn('is_balanced', bs)

    def test_income_statement_structure(self):
        is_report = income_statement(
            period_start=date.today().replace(day=1),
            period_end=date.today(),
        )
        self.assertIn('period_start', is_report)
        self.assertIn('period_end', is_report)
        self.assertIn('revenue', is_report)
        self.assertIn('expenses', is_report)
        self.assertIn('total_revenue', is_report)
        self.assertIn('net_income', is_report)

    def test_cash_flow_basic_structure(self):
        cf = cash_flow_basic(
            period_start=date.today().replace(day=1),
            period_end=date.today(),
        )
        self.assertIn('period_start', cf)
        self.assertIn('period_end', cf)
        self.assertIn('opening_balance', cf)
        self.assertIn('total_inflow', cf)
        self.assertIn('total_outflow', cf)
        self.assertIn('net_cash_flow', cf)
        self.assertIn('closing_balance', cf)
