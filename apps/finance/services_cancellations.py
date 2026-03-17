"""Cancellation, refund, and operational exception services.

Handles the financial impact of order cancellations according to the plan:
- Total cancellation before/after settlement
- Refund processing
- Processor fee loss tracking
- Organizer recovery (accounts receivable)
- Ledger reversal entries
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.events.models import Order

from .models import JournalEntry, PayableLine, Payout, SettlementRun
from .services_ledger import (
    create_journal_entry,
    reverse_journal_entry,
    ZERO,
)

logger = logging.getLogger('finance.cancellations')


@transaction.atomic
def process_order_cancellation(
    *,
    order: Order,
    cancellation_reason: str = '',
    refund_amount: Decimal | None = None,
    processor_fee_loss: Decimal = ZERO,
    refund_responsibility: str = 'tuki',
    user=None,
) -> dict:
    """Process a full order cancellation with financial impact.

    Handles:
    1. Voiding open payable lines
    2. Recording processor fee loss
    3. Creating recovery receivable if organizer is responsible
    4. Reversing any posted journal entries
    5. Updating settlement if applicable

    Returns summary dict of all actions taken.
    """
    now = timezone.now()
    actions = {
        'payables_voided': 0,
        'settlements_adjusted': 0,
        'journal_entries_reversed': 0,
        'processor_fee_loss_recorded': False,
        'recovery_created': False,
    }

    order.cancellation_reason = cancellation_reason
    order.cancellation_date = now
    order.processor_fee_loss_amount = processor_fee_loss
    order.refund_responsibility = refund_responsibility

    if refund_amount is not None:
        order.refunded_amount = refund_amount
        order.refund_reason = order.refund_reason or cancellation_reason

    update_fields = [
        'cancellation_reason', 'cancellation_date',
        'processor_fee_loss_amount', 'refund_responsibility',
        'refunded_amount', 'refund_reason', 'updated_at',
    ]
    order.save(update_fields=update_fields)

    voided = PayableLine.objects.filter(
        order=order,
        status__in=('open', 'batched'),
    ).update(status='voided')
    actions['payables_voided'] = voided

    settlements = SettlementRun.objects.filter(
        lines__order=order,
        status__in=('draft', 'calculated'),
    ).distinct()
    for settlement in settlements:
        settlement.lines.filter(order=order).delete()
        _recalculate_settlement_totals(settlement)
        actions['settlements_adjusted'] += 1

    entries = JournalEntry.objects.filter(
        source_type='payment',
        source_id__in=[
            str(p.id) for p in order.payments.all()
        ] if hasattr(order, 'payments') else [],
        status='posted',
    )
    for entry in entries:
        reverse_journal_entry(
            entry,
            description=f'Cancellation reversal: Order {order.order_number}',
            created_by=user,
        )
        actions['journal_entries_reversed'] += 1

    if processor_fee_loss > ZERO:
        _record_processor_fee_loss(order, processor_fee_loss)
        actions['processor_fee_loss_recorded'] = True

    if refund_responsibility == 'organizer' and processor_fee_loss > ZERO:
        _create_organizer_recovery(order, processor_fee_loss, user)
        actions['recovery_created'] = True

    logger.info(
        'Order %s cancelled: reason=%s refund=%s processor_loss=%s responsibility=%s actions=%s',
        order.order_number, cancellation_reason, refund_amount,
        processor_fee_loss, refund_responsibility, actions,
    )

    return actions


def _recalculate_settlement_totals(settlement: SettlementRun):
    """Recalculate settlement aggregates after line removal."""
    from django.db.models import Sum
    agg = settlement.lines.aggregate(
        gross=Sum('gross_amount'),
        fee=Sum('platform_fee_amount'),
        payable=Sum('payable_amount'),
    )
    settlement.gross_collected = agg['gross'] or ZERO
    settlement.platform_fee_recognized = agg['fee'] or ZERO
    settlement.payable_amount = agg['payable'] or ZERO
    settlement.save(update_fields=[
        'gross_collected', 'platform_fee_recognized', 'payable_amount', 'updated_at',
    ])


def _record_processor_fee_loss(order: Order, amount: Decimal):
    """Post journal entry for non-recoverable processor fee loss.

    Dr Processor fee loss expense
    Cr Cash/Bank
    """
    create_journal_entry(
        source_type='order',
        source_id=str(order.id),
        posting_event='processor_fee_loss',
        description=f'Processor fee loss on cancellation: Order {order.order_number}',
        reference=order.order_number,
        lines=[
            {'account_code': '5.1.04', 'debit': amount, 'credit': ZERO, 'order_id': str(order.id)},
            {'account_code': '1.1.02', 'debit': ZERO, 'credit': amount, 'order_id': str(order.id)},
        ],
    )


def _create_organizer_recovery(order: Order, amount: Decimal, user=None):
    """Create an accounts receivable entry for organizer recovery.

    Dr Accounts receivable – organizers
    Cr Processor fee loss reversal
    """
    from .services import _get_order_organizer, get_or_create_organizer_payee

    organizer = _get_order_organizer(order)
    if not organizer:
        logger.warning('Cannot create organizer recovery for order %s: no organizer found', order.id)
        return

    payee = get_or_create_organizer_payee(organizer)

    PayableLine.objects.create(
        payee=payee,
        order=order,
        source_type='manual_adjustment',
        source_reference=f'recovery:{order.id}:processor_fee',
        source_label=f'Recovery: processor fee loss – {order.order_number}',
        status='open',
        maturity_status='available',
        gross_amount=-amount,
        platform_fee_amount=ZERO,
        payable_amount=-amount,
        currency='CLP',
        effective_at=timezone.now(),
        recovery_status='pending',
        metadata={
            'recovery_type': 'processor_fee_loss',
            'original_order_id': str(order.id),
            'order_number': order.order_number,
            'cancellation_reason': order.cancellation_reason,
        },
    )

    create_journal_entry(
        source_type='order',
        source_id=str(order.id),
        posting_event='organizer_recovery_receivable',
        description=f'AR organizer recovery: Order {order.order_number}',
        reference=order.order_number,
        lines=[
            {
                'account_code': '1.1.06',
                'debit': amount,
                'credit': ZERO,
                'order_id': str(order.id),
                'organizer_id': str(organizer.id),
            },
            {
                'account_code': '5.1.04',
                'debit': ZERO,
                'credit': amount,
                'order_id': str(order.id),
                'description': 'Reversal of processor fee loss (transferred to organizer)',
            },
        ],
    )

    logger.info(
        'Recovery receivable created: order=%s organizer=%s amount=%s',
        order.order_number, organizer.name, amount,
    )


@transaction.atomic
def process_payout_clawback(
    *,
    payout: Payout,
    reason: str = '',
    user=None,
) -> dict:
    """Handle clawback of an already-paid payout due to cancellation.

    Creates a negative payable line to recover the funds on next settlement.
    """
    if payout.status != 'paid':
        raise ValueError(f'Cannot claw back payout in status {payout.status}')

    payee = payout.payee
    PayableLine.objects.create(
        payee=payee,
        source_type='manual_adjustment',
        source_reference=f'clawback:{payout.id}',
        source_label=f'Clawback: Payout {payout.reference or payout.id}',
        status='open',
        maturity_status='available',
        gross_amount=ZERO,
        platform_fee_amount=ZERO,
        payable_amount=-payout.amount,
        currency=payout.currency,
        effective_at=timezone.now(),
        recovery_status='pending',
        metadata={
            'recovery_type': 'payout_clawback',
            'original_payout_id': str(payout.id),
            'reason': reason,
        },
    )

    entry = JournalEntry.objects.filter(
        source_type='payout',
        source_id=str(payout.id),
        status='posted',
    ).first()
    if entry:
        reverse_journal_entry(
            entry,
            description=f'Clawback reversal: Payout {payout.reference or payout.id}',
            created_by=user,
        )

    logger.info('Payout %s clawback processed: amount=%s reason=%s', payout.id, payout.amount, reason)

    return {
        'payout_id': str(payout.id),
        'clawback_amount': float(payout.amount),
        'journal_reversed': entry is not None,
    }
