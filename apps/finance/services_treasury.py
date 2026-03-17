"""Treasury position and bank reconciliation services."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    BankAccount,
    BankBalanceSnapshot,
    BankStatementLine,
    PayableLine,
    ProcessorSettlement,
)

ZERO = Decimal('0')


def get_treasury_position(*, as_of=None) -> dict:
    """Calculate treasury position showing real cash, book balance, and breakdowns."""
    as_of = as_of or timezone.localdate()

    bank_cash_actual = ZERO
    for account in BankAccount.objects.filter(is_active=True):
        snapshot = BankBalanceSnapshot.objects.filter(
            bank_account=account,
            snapshot_date__lte=as_of,
        ).order_by('-snapshot_date').first()
        if snapshot:
            bank_cash_actual += snapshot.balance

    processor_in_transit = ProcessorSettlement.objects.filter(
        status__in=('reported', 'matched'),
    ).aggregate(total=Sum('net_amount'))['total'] or ZERO

    third_party_retained = PayableLine.objects.filter(
        status='open',
        commercial_mode='collect_total',
    ).aggregate(total=Sum('payable_amount'))['total'] or ZERO

    own_cash_theoretical = bank_cash_actual + processor_in_transit - third_party_retained
    own_cash_available = bank_cash_actual - third_party_retained

    return {
        'as_of': as_of.isoformat(),
        'bank_cash_actual': float(bank_cash_actual),
        'processor_clearing_in_transit': float(processor_in_transit),
        'third_party_funds_retained': float(third_party_retained),
        'own_cash_theoretical': float(own_cash_theoretical),
        'own_cash_available': float(own_cash_available),
        'bank_accounts': [
            _bank_account_summary(account, as_of)
            for account in BankAccount.objects.filter(is_active=True)
        ],
    }


def _bank_account_summary(account: BankAccount, as_of) -> dict:
    snapshot = BankBalanceSnapshot.objects.filter(
        bank_account=account,
        snapshot_date__lte=as_of,
    ).order_by('-snapshot_date').first()

    return {
        'id': str(account.id),
        'name': account.name,
        'bank_name': account.bank_name,
        'currency': account.currency,
        'balance': float(snapshot.balance) if snapshot else 0,
        'snapshot_date': snapshot.snapshot_date.isoformat() if snapshot else None,
    }
