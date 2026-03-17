"""Ledger posting engine with idempotent double-entry journal entries."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import JournalEntry, JournalLine, LedgerAccount

logger = logging.getLogger('finance.ledger')
ZERO = Decimal('0')


def _get_account(code: str) -> LedgerAccount:
    try:
        return LedgerAccount.objects.get(code=code)
    except LedgerAccount.DoesNotExist:
        raise ValueError(f'Ledger account {code} does not exist')


@transaction.atomic
def create_journal_entry(
    *,
    source_type: str,
    source_id: str,
    posting_event: str,
    lines: list[dict],
    entry_date=None,
    posting_date=None,
    description: str = '',
    reference: str = '',
    created_by=None,
    metadata: dict | None = None,
    auto_post: bool = True,
) -> JournalEntry | None:
    """Create an idempotent journal entry with lines.

    Returns None if entry already exists (idempotency).
    Raises ValueError if lines don't balance.

    Each line dict: {
        'account_code': str,
        'debit': Decimal,
        'credit': Decimal,
        'currency': str (optional, default 'CLP'),
        'description': str (optional),
        # optional dimension FKs as keyword args:
        'organizer_id', 'vendor_id', 'order_id', etc.
    }
    """
    idempotency_key = f'{source_type}:{source_id}:{posting_event}'

    existing = JournalEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing and existing.status in ('posted', 'draft'):
        logger.debug('Idempotent skip: %s already exists as %s', idempotency_key, existing.status)
        return None

    total_debit = sum(Decimal(str(l.get('debit', 0))) for l in lines)
    total_credit = sum(Decimal(str(l.get('credit', 0))) for l in lines)
    if total_debit != total_credit:
        raise ValueError(
            f'Journal entry not balanced: Dr {total_debit} != Cr {total_credit}'
        )

    today = timezone.localdate()

    try:
        entry = JournalEntry.objects.create(
            entry_date=entry_date or today,
            posting_date=posting_date or today,
            reference=reference,
            source_type=source_type,
            source_id=source_id,
            posting_event=posting_event,
            idempotency_key=idempotency_key,
            description=description,
            status='posted' if auto_post else 'draft',
            created_by=created_by,
            metadata=metadata or {},
        )
    except IntegrityError:
        logger.debug('IntegrityError (concurrent idempotency) for %s', idempotency_key)
        return None

    for line_data in lines:
        account = _get_account(line_data['account_code'])
        debit = Decimal(str(line_data.get('debit', 0)))
        credit = Decimal(str(line_data.get('credit', 0)))
        functional = debit - credit

        JournalLine.objects.create(
            journal_entry=entry,
            ledger_account=account,
            debit_amount=debit,
            credit_amount=credit,
            currency=line_data.get('currency', 'CLP'),
            functional_amount=functional,
            description=line_data.get('description', ''),
            organizer_id=line_data.get('organizer_id'),
            vendor_id=line_data.get('vendor_id'),
            related_party_id=line_data.get('related_party_id'),
            order_id=line_data.get('order_id'),
            payment_id=line_data.get('payment_id'),
            external_revenue_record_id=line_data.get('external_revenue_record_id'),
            settlement_run_id=line_data.get('settlement_run_id'),
            payable_line_id=line_data.get('payable_line_id'),
            payout_id=line_data.get('payout_id'),
            vendor_bill_id=line_data.get('vendor_bill_id'),
            vendor_payment_id=line_data.get('vendor_payment_id'),
            processor_settlement_id=line_data.get('processor_settlement_id'),
            bank_statement_line_id=line_data.get('bank_statement_line_id'),
            metadata=line_data.get('metadata', {}),
        )

    logger.info(
        'Journal entry %s created: event=%s key=%s lines=%d Dr=%s',
        entry.id, posting_event, idempotency_key, len(lines), total_debit,
    )

    return entry


@transaction.atomic
def reverse_journal_entry(
    entry: JournalEntry,
    *,
    description: str = '',
    created_by=None,
) -> JournalEntry:
    """Create a reversal entry for an existing posted entry."""
    if entry.status != 'posted':
        raise ValueError(f'Cannot reverse entry in status {entry.status}')

    reversal_key = f'{entry.source_type}:{entry.source_id}:{entry.posting_event}:reversal'

    existing_reversal = JournalEntry.objects.filter(idempotency_key=reversal_key).first()
    if existing_reversal:
        return existing_reversal

    today = timezone.localdate()
    reversal = JournalEntry.objects.create(
        entry_date=today,
        posting_date=today,
        reference=f'REV-{entry.reference}',
        source_type=entry.source_type,
        source_id=entry.source_id,
        posting_event=f'{entry.posting_event}:reversal',
        idempotency_key=reversal_key,
        description=description or f'Reversal of {entry.reference or entry.idempotency_key}',
        status='posted',
        reversal_of=entry,
        created_by=created_by,
        metadata={'reversed_entry_id': str(entry.id)},
    )

    for orig_line in entry.lines.all():
        JournalLine.objects.create(
            journal_entry=reversal,
            ledger_account=orig_line.ledger_account,
            debit_amount=orig_line.credit_amount,
            credit_amount=orig_line.debit_amount,
            currency=orig_line.currency,
            functional_amount=-orig_line.functional_amount,
            description=f'Reversal: {orig_line.description}',
            organizer=orig_line.organizer,
            vendor=orig_line.vendor,
            related_party=orig_line.related_party,
            order=orig_line.order,
            payment=orig_line.payment,
            external_revenue_record=orig_line.external_revenue_record,
            settlement_run=orig_line.settlement_run,
            payable_line=orig_line.payable_line,
            payout=orig_line.payout,
            vendor_bill=orig_line.vendor_bill,
            vendor_payment=orig_line.vendor_payment,
            processor_settlement=orig_line.processor_settlement,
            bank_statement_line=orig_line.bank_statement_line,
        )

    entry.status = 'reversed'
    entry.save(update_fields=['status', 'updated_at'])

    logger.info('Journal entry %s reversed → reversal %s', entry.id, reversal.id)

    return reversal


# ---------------------------------------------------------------------------
# Standard posting functions for business events
# ---------------------------------------------------------------------------

def post_payment_completed(*, order, payment, account_codes: dict | None = None):
    """Post journal entry for a completed payment (modalidad 1: collect_total).

    Dr Processor clearing / Cash
    Cr Third-party funds payable
    """
    codes = account_codes or {
        'cash': '1.1.02',
        'third_party_funds': '2.1.10',
    }
    amount = Decimal(str(order.total or 0))
    if amount <= ZERO:
        return None

    return create_journal_entry(
        source_type='payment',
        source_id=str(payment.id),
        posting_event='payment_completed',
        description=f'Payment completed: Order {order.order_number}',
        reference=order.order_number,
        lines=[
            {'account_code': codes['cash'], 'debit': amount, 'credit': ZERO, 'order_id': str(order.id), 'payment_id': str(payment.id)},
            {'account_code': codes['third_party_funds'], 'debit': ZERO, 'credit': amount, 'order_id': str(order.id)},
        ],
    )


def post_commission_recognition(*, settlement_run, account_codes: dict | None = None):
    """Post journal entry for commission recognition (modalidad 1).

    Dr Third-party funds payable
    Cr Commission revenue
    """
    codes = account_codes or {
        'third_party_funds': '2.1.10',
        'commission_revenue': '4.1.01',
    }
    amount = settlement_run.platform_fee_recognized
    if amount <= ZERO:
        return None

    return create_journal_entry(
        source_type='settlement_run',
        source_id=str(settlement_run.id),
        posting_event='commission_recognized',
        description=f'Commission recognized: Settlement {settlement_run.id}',
        lines=[
            {'account_code': codes['third_party_funds'], 'debit': amount, 'credit': ZERO, 'settlement_run_id': str(settlement_run.id), 'organizer_id': str(settlement_run.organizer_id)},
            {'account_code': codes['commission_revenue'], 'debit': ZERO, 'credit': amount, 'settlement_run_id': str(settlement_run.id)},
        ],
    )


def post_partner_payable(*, settlement_run, account_codes: dict | None = None):
    """Post journal entry for partner payable recognition.

    Dr Third-party funds payable
    Cr Accounts payable – partners
    """
    codes = account_codes or {
        'third_party_funds': '2.1.10',
        'ap_partners': '2.1.11',
    }
    amount = settlement_run.payable_amount
    if amount <= ZERO:
        return None

    return create_journal_entry(
        source_type='settlement_run',
        source_id=str(settlement_run.id),
        posting_event='partner_payable_recognized',
        description=f'Partner payable: Settlement {settlement_run.id}',
        lines=[
            {'account_code': codes['third_party_funds'], 'debit': amount, 'credit': ZERO, 'settlement_run_id': str(settlement_run.id), 'organizer_id': str(settlement_run.organizer_id)},
            {'account_code': codes['ap_partners'], 'debit': ZERO, 'credit': amount, 'organizer_id': str(settlement_run.organizer_id)},
        ],
    )


def post_payout_paid(*, payout, account_codes: dict | None = None):
    """Post journal entry for partner payout.

    Dr Accounts payable – partners
    Cr Cash / Bank
    """
    codes = account_codes or {
        'ap_partners': '2.1.11',
        'cash': '1.1.02',
    }
    amount = payout.amount
    if amount <= ZERO:
        return None

    return create_journal_entry(
        source_type='payout',
        source_id=str(payout.id),
        posting_event='payout_paid',
        description=f'Payout to {payout.payee.display_name}',
        lines=[
            {'account_code': codes['ap_partners'], 'debit': amount, 'credit': ZERO, 'payout_id': str(payout.id), 'organizer_id': str(payout.payee.organizer_id) if payout.payee.organizer_id else None},
            {'account_code': codes['cash'], 'debit': ZERO, 'credit': amount, 'payout_id': str(payout.id)},
        ],
    )


def post_vendor_bill_posted(*, vendor_bill, account_codes: dict | None = None):
    """Post journal entry for a posted vendor bill.

    For each expense line, creates appropriate debit based on tax treatment.
    Cr Accounts payable – vendors
    """
    codes = account_codes or {
        'ap_vendors': '2.1.20',
        'expense_default': '5.1.01',
        'vat_credit': '1.1.05',
    }
    lines = []
    total = ZERO

    for exp_line in vendor_bill.expense_lines.select_related('tax_treatment'):
        tax = exp_line.tax_treatment
        if tax and tax.is_recoverable:
            lines.append({
                'account_code': codes['expense_default'],
                'debit': exp_line.net_amount,
                'credit': ZERO,
                'vendor_bill_id': str(vendor_bill.id),
                'vendor_id': str(vendor_bill.vendor_id),
                'description': exp_line.description,
            })
            lines.append({
                'account_code': codes['vat_credit'],
                'debit': exp_line.tax_amount,
                'credit': ZERO,
                'vendor_bill_id': str(vendor_bill.id),
            })
            total += exp_line.net_amount + exp_line.tax_amount
        else:
            lines.append({
                'account_code': codes['expense_default'],
                'debit': exp_line.gross_amount,
                'credit': ZERO,
                'vendor_bill_id': str(vendor_bill.id),
                'vendor_id': str(vendor_bill.vendor_id),
                'description': exp_line.description,
            })
            total += exp_line.gross_amount

    if total <= ZERO:
        return None

    lines.append({
        'account_code': codes['ap_vendors'],
        'debit': ZERO,
        'credit': total,
        'vendor_bill_id': str(vendor_bill.id),
        'vendor_id': str(vendor_bill.vendor_id),
    })

    return create_journal_entry(
        source_type='vendor_bill',
        source_id=str(vendor_bill.id),
        posting_event='vendor_bill_posted',
        description=f'Vendor bill: {vendor_bill.vendor.name} – {vendor_bill.bill_number}',
        reference=vendor_bill.bill_number,
        lines=lines,
    )


def post_vendor_payment_completed(*, vendor_payment, account_codes: dict | None = None):
    """Post journal entry for a completed vendor payment.

    Dr Accounts payable – vendors
    Cr Cash / Bank
    """
    codes = account_codes or {
        'ap_vendors': '2.1.20',
        'cash': '1.1.02',
    }
    amount = vendor_payment.amount
    if amount <= ZERO:
        return None

    return create_journal_entry(
        source_type='vendor_payment',
        source_id=str(vendor_payment.id),
        posting_event='vendor_payment_completed',
        description=f'Vendor payment: {vendor_payment.vendor.name}',
        lines=[
            {'account_code': codes['ap_vendors'], 'debit': amount, 'credit': ZERO, 'vendor_payment_id': str(vendor_payment.id), 'vendor_id': str(vendor_payment.vendor_id)},
            {'account_code': codes['cash'], 'debit': ZERO, 'credit': amount, 'vendor_payment_id': str(vendor_payment.id)},
        ],
    )


def post_service_fee_collected(*, order, payment, account_codes: dict | None = None):
    """Post journal entry for modalidad 3: service fee collection.

    Dr Cash / Bank
    Cr Service fee revenue
    """
    codes = account_codes or {
        'cash': '1.1.02',
        'service_fee_revenue': '4.1.02',
    }
    amount = Decimal(str(order.service_fee_effective or order.service_fee or 0))
    if amount <= ZERO:
        return None

    return create_journal_entry(
        source_type='payment',
        source_id=str(payment.id),
        posting_event='service_fee_collected',
        description=f'Service fee: Order {order.order_number}',
        reference=order.order_number,
        lines=[
            {'account_code': codes['cash'], 'debit': amount, 'credit': ZERO, 'order_id': str(order.id), 'payment_id': str(payment.id)},
            {'account_code': codes['service_fee_revenue'], 'debit': ZERO, 'credit': amount, 'order_id': str(order.id)},
        ],
    )
