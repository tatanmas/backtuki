"""Financial report services: trial balance, balance sheet, income statement, cash flow."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Sum, Q
from django.utils import timezone

from .models import JournalLine, LedgerAccount

ZERO = Decimal('0')


def trial_balance(*, as_of=None, posted_only: bool = True) -> list[dict]:
    """Generate trial balance from journal lines."""
    as_of = as_of or timezone.localdate()

    status_filter = Q(journal_entry__status='posted') if posted_only else Q()
    date_filter = Q(journal_entry__posting_date__lte=as_of)

    accounts = LedgerAccount.objects.filter(is_active=True).order_by('code')
    result = []

    for account in accounts:
        agg = JournalLine.objects.filter(
            status_filter,
            date_filter,
            ledger_account=account,
        ).aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount'),
        )
        debit = agg['total_debit'] or ZERO
        credit = agg['total_credit'] or ZERO
        balance = debit - credit

        if debit == ZERO and credit == ZERO:
            continue

        result.append({
            'account_code': account.code,
            'account_name': account.name,
            'account_type': account.account_type,
            'debit': float(debit),
            'credit': float(credit),
            'balance': float(balance),
        })

    return result


def balance_sheet(*, as_of=None) -> dict:
    """Generate balance sheet from ledger."""
    tb = trial_balance(as_of=as_of)

    assets = []
    liabilities = []
    equity = []
    total_assets = ZERO
    total_liabilities = ZERO
    total_equity = ZERO

    revenue_total = ZERO
    expense_total = ZERO

    for row in tb:
        balance = Decimal(str(row['balance']))
        account_type = row['account_type']

        if account_type == 'asset':
            assets.append(row)
            total_assets += balance
        elif account_type == 'liability':
            liabilities.append(row)
            total_liabilities += abs(balance)
        elif account_type == 'equity':
            equity.append(row)
            total_equity += abs(balance)
        elif account_type == 'revenue':
            revenue_total += abs(balance)
        elif account_type == 'expense':
            expense_total += balance

    retained_earnings = revenue_total - expense_total
    total_equity += retained_earnings

    return {
        'as_of': (as_of or timezone.localdate()).isoformat(),
        'assets': assets,
        'liabilities': liabilities,
        'equity': equity,
        'retained_earnings': float(retained_earnings),
        'total_assets': float(total_assets),
        'total_liabilities': float(total_liabilities),
        'total_equity': float(total_equity),
        'total_liabilities_and_equity': float(total_liabilities + total_equity),
        'is_balanced': abs(total_assets - (total_liabilities + total_equity)) < Decimal('0.01'),
    }


def income_statement(*, period_start=None, period_end=None) -> dict:
    """Generate income statement from ledger for a given period."""
    period_end = period_end or timezone.localdate()
    period_start = period_start or period_end.replace(day=1)

    date_filter = Q(
        journal_entry__posting_date__gte=period_start,
        journal_entry__posting_date__lte=period_end,
        journal_entry__status='posted',
    )

    revenue_lines = JournalLine.objects.filter(
        date_filter,
        ledger_account__account_type='revenue',
    ).values(
        'ledger_account__code',
        'ledger_account__name',
    ).annotate(
        total_debit=Sum('debit_amount'),
        total_credit=Sum('credit_amount'),
    )

    expense_lines = JournalLine.objects.filter(
        date_filter,
        ledger_account__account_type='expense',
    ).values(
        'ledger_account__code',
        'ledger_account__name',
    ).annotate(
        total_debit=Sum('debit_amount'),
        total_credit=Sum('credit_amount'),
    )

    revenue_items = []
    total_revenue = ZERO
    for row in revenue_lines:
        amount = (row['total_credit'] or ZERO) - (row['total_debit'] or ZERO)
        revenue_items.append({
            'account_code': row['ledger_account__code'],
            'account_name': row['ledger_account__name'],
            'amount': float(amount),
        })
        total_revenue += amount

    expense_items = []
    total_expenses = ZERO
    for row in expense_lines:
        amount = (row['total_debit'] or ZERO) - (row['total_credit'] or ZERO)
        expense_items.append({
            'account_code': row['ledger_account__code'],
            'account_name': row['ledger_account__name'],
            'amount': float(amount),
        })
        total_expenses += amount

    return {
        'period_start': period_start.isoformat(),
        'period_end': period_end.isoformat(),
        'revenue': revenue_items,
        'expenses': expense_items,
        'total_revenue': float(total_revenue),
        'total_expenses': float(total_expenses),
        'net_income': float(total_revenue - total_expenses),
    }


def cash_flow_basic(*, period_start=None, period_end=None) -> dict:
    """Generate basic cash flow from ledger (changes in cash accounts)."""
    period_end = period_end or timezone.localdate()
    period_start = period_start or period_end.replace(day=1)

    date_filter = Q(
        journal_entry__posting_date__gte=period_start,
        journal_entry__posting_date__lte=period_end,
        journal_entry__status='posted',
    )

    cash_accounts = LedgerAccount.objects.filter(
        account_type='asset',
        subtype__in=['cash', 'bank', 'processor_clearing'],
        is_active=True,
    )

    cash_movements = JournalLine.objects.filter(
        date_filter,
        ledger_account__in=cash_accounts,
    ).values(
        'journal_entry__posting_event',
    ).annotate(
        total_debit=Sum('debit_amount'),
        total_credit=Sum('credit_amount'),
    )

    items = []
    total_inflow = ZERO
    total_outflow = ZERO

    for row in cash_movements:
        debit = row['total_debit'] or ZERO
        credit = row['total_credit'] or ZERO
        net = debit - credit
        items.append({
            'posting_event': row['journal_entry__posting_event'],
            'inflow': float(debit),
            'outflow': float(credit),
            'net': float(net),
        })
        total_inflow += debit
        total_outflow += credit

    opening_balance = ZERO
    for account in cash_accounts:
        agg = JournalLine.objects.filter(
            journal_entry__posting_date__lt=period_start,
            journal_entry__status='posted',
            ledger_account=account,
        ).aggregate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount'),
        )
        opening_balance += (agg['total_debit'] or ZERO) - (agg['total_credit'] or ZERO)

    return {
        'period_start': period_start.isoformat(),
        'period_end': period_end.isoformat(),
        'opening_balance': float(opening_balance),
        'total_inflow': float(total_inflow),
        'total_outflow': float(total_outflow),
        'net_cash_flow': float(total_inflow - total_outflow),
        'closing_balance': float(opening_balance + total_inflow - total_outflow),
        'movements': items,
    }
