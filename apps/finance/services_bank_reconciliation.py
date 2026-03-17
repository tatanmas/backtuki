"""
Bank reconciliation services: classify statement lines, match to payouts/vendor payments.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from django.db import transaction
from django.db.models import Q, Count, Sum
from django.utils import timezone

from .models import (
    BankAccount,
    BankStatementLine,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Payout,
    ProcessorSettlement,
    VendorPayment,
)

logger = logging.getLogger(__name__)

ZERO = Decimal('0')


def list_statement_lines(
    *,
    bank_account_id: Optional[UUID] = None,
    status: Optional[str] = None,
    movement_type: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[BankStatementLine], int]:
    """List bank statement lines with filters. Returns (lines, total_count)."""
    from django.db.models import Count, Q

    qs = BankStatementLine.objects.select_related(
        'bank_account',
        'matched_payout',
        'matched_payout__payee',
        'matched_vendor_payment',
        'matched_vendor_payment__vendor',
        'matched_processor_settlement',
        'matched_journal_entry',
    ).order_by('-statement_date', '-created_at')

    if bank_account_id:
        qs = qs.filter(bank_account_id=bank_account_id)
    if status:
        qs = qs.filter(status=status)
    if movement_type:
        qs = qs.filter(movement_type=movement_type)
    if from_date:
        qs = qs.filter(statement_date__gte=from_date)
    if to_date:
        qs = qs.filter(statement_date__lte=to_date)

    total = qs.count()
    lines = list(qs[offset : offset + limit])
    return lines, total


def get_matchable_payouts(
    *,
    bank_account_id: Optional[UUID] = None,
    amount: Optional[Decimal] = None,
    limit: int = 50,
) -> list[Payout]:
    """Payouts with status=paid that are not yet matched to a bank line."""
    qs = Payout.objects.filter(
        status='paid',
        bank_statement_lines__isnull=True,
    ).select_related('payee').order_by('-paid_at')

    if amount is not None:
        qs = qs.filter(amount=amount)
    return list(qs[:limit])


def get_matchable_vendor_payments(
    *,
    amount: Optional[Decimal] = None,
    limit: int = 50,
) -> list[VendorPayment]:
    """Vendor payments completed that are not yet matched to a bank line."""
    qs = VendorPayment.objects.filter(
        status='completed',
        bank_statement_lines__isnull=True,
    ).select_related('vendor').order_by('-payment_date')

    if amount is not None:
        qs = qs.filter(amount=amount)
    return list(qs[:limit])


def get_matchable_processor_settlements(
    *,
    amount: Optional[Decimal] = None,
    limit: int = 50,
) -> list[ProcessorSettlement]:
    """Processor settlements not yet matched to a bank line."""
    qs = ProcessorSettlement.objects.filter(
        bank_statement_lines__isnull=True,
    ).order_by('-payment_date')

    if amount is not None:
        qs = qs.filter(net_amount=amount)
    return list(qs[:limit])


def classify_statement_line(
    *,
    line_id: UUID,
    movement_type: str,
    classification_note: str = '',
    payout_id: Optional[UUID] = None,
    vendor_payment_id: Optional[UUID] = None,
    processor_settlement_id: Optional[UUID] = None,
    create_manual_expense: bool = False,
    expense_ledger_account_code: Optional[str] = None,
    user=None,
) -> BankStatementLine:
    """
    Classify a bank statement line. Sets movement_type, status, and links to payout/vendor_payment/processor_settlement.
    For manual expense: creates a JournalEntry and links it.
    """
    with transaction.atomic():
        line = BankStatementLine.objects.select_for_update().get(id=line_id)

        # Clear previous matches
        line.matched_payout_id = None
        line.matched_vendor_payment_id = None
        line.matched_processor_settlement_id = None
        line.matched_journal_entry_id = None

        line.movement_type = movement_type
        line.classification_note = classification_note.strip()

        if payout_id:
            payout = Payout.objects.get(id=payout_id, status='paid')
            line.matched_payout = payout
            line.status = 'matched'
        elif vendor_payment_id:
            vp = VendorPayment.objects.get(id=vendor_payment_id, status='completed')
            line.matched_vendor_payment = vp
            line.status = 'matched'
        elif processor_settlement_id:
            ps = ProcessorSettlement.objects.get(id=processor_settlement_id)
            line.matched_processor_settlement = ps
            line.status = 'matched'
        elif create_manual_expense and expense_ledger_account_code:
            # Create journal entry for manual expense
            ledger_account = LedgerAccount.objects.get(code=expense_ledger_account_code, is_active=True)
            entry = _create_expense_journal_entry(
                line=line,
                expense_account=ledger_account,
                user=user,
            )
            line.matched_journal_entry = entry
            line.status = 'matched'
        elif movement_type == 'other' or not (payout_id or vendor_payment_id or processor_settlement_id):
            # Just set type and note, maybe ignored
            line.status = 'matched' if movement_type else 'imported'

        line.save(update_fields=[
            'movement_type', 'classification_note', 'status',
            'matched_payout_id', 'matched_vendor_payment_id',
            'matched_processor_settlement_id', 'matched_journal_entry_id',
            'updated_at',
        ])
        logger.info(
            'Bank statement line %s classified: movement_type=%s status=%s',
            line_id, movement_type, line.status,
        )
        return line


def _create_expense_journal_entry(
    *,
    line: BankStatementLine,
    expense_account: LedgerAccount,
    user=None,
) -> JournalEntry:
    """Create a journal entry for a manual expense from a bank statement line."""
    from .services_ledger import create_journal_entry

    amount = abs(line.amount) if line.amount < ZERO else line.amount
    bank_account = LedgerAccount.objects.filter(
        code__startswith='1.1',
        account_type='asset',
        is_active=True,
    ).first()
    if not bank_account:
        bank_account = LedgerAccount.objects.filter(account_type='asset', is_active=True).first()
    if not bank_account:
        bank_account = expense_account

    lines = [
        {
            'account_code': expense_account.code,
            'debit': amount,
            'credit': ZERO,
            'description': line.description or line.classification_note or 'Gasto bancario',
        },
        {
            'account_code': bank_account.code,
            'debit': ZERO,
            'credit': amount,
            'description': f'Banco {line.bank_account.name}',
            'bank_statement_line_id': str(line.id),
        },
    ]
    entry = create_journal_entry(
        entry_date=line.statement_date,
        posting_date=line.statement_date,
        source_type='bank_reconciliation',
        source_id=line.id,
        posting_event='manual_expense',
        description=line.description or 'Gasto desde conciliación bancaria',
        lines=lines,
        created_by=user,
    )
    if entry is None:
        entry = JournalEntry.objects.get(
            idempotency_key=f'bank_reconciliation:{line.id}:manual_expense'
        )
    return entry


def unclassify_statement_line(line_id: UUID) -> BankStatementLine:
    """Clear classification and reset status to imported."""
    with transaction.atomic():
        line = BankStatementLine.objects.select_for_update().get(id=line_id)
        line.movement_type = ''
        line.classification_note = ''
        line.status = 'imported'
        line.matched_payout_id = None
        line.matched_vendor_payment_id = None
        line.matched_processor_settlement_id = None
        line.matched_journal_entry_id = None
        line.save(update_fields=[
            'movement_type', 'classification_note', 'status',
            'matched_payout_id', 'matched_vendor_payment_id',
            'matched_processor_settlement_id', 'matched_journal_entry_id',
            'updated_at',
        ])
        logger.info('Bank statement line %s unclassified', line_id)
        return line


def ignore_statement_line(line_id: UUID) -> BankStatementLine:
    """Mark line as ignored (e.g. duplicate, internal transfer to same bank)."""
    line = BankStatementLine.objects.get(id=line_id)
    line.status = 'ignored'
    line.movement_type = line.movement_type or 'other'
    line.save(update_fields=['status', 'movement_type', 'updated_at'])
    logger.info('Bank statement line %s ignored', line_id)
    return line


def get_reconciliation_summary(bank_account_id: UUID) -> dict:
    """Summary of imported vs matched vs ignored lines for a bank account."""
    qs = BankStatementLine.objects.filter(bank_account_id=bank_account_id)
    by_status = dict(qs.values('status').annotate(count=Count('id')).values_list('status', 'count'))
    amounts = qs.aggregate(
        total_imported=Sum('amount', filter=Q(status='imported')),
        total_matched=Sum('amount', filter=Q(status='matched')),
        total_ignored=Sum('amount', filter=Q(status='ignored')),
    )
    return {
        'imported_count': by_status.get('imported', 0),
        'matched_count': by_status.get('matched', 0),
        'partially_matched_count': by_status.get('partially_matched', 0),
        'ignored_count': by_status.get('ignored', 0),
        'total_imported_amount': float(amounts['total_imported'] or 0),
        'total_matched_amount': float(amounts['total_matched'] or 0),
        'total_ignored_amount': float(amounts['total_ignored'] or 0),
    }
