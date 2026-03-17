"""Settlement calculation and custody position services."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.events.models import Order
from core.revenue_system import order_revenue_eligible_q

from .models import (
    CommercialPolicy,
    ExternalRevenueRecord,
    PayableLine,
    PayeeAccount,
    SettlementLine,
    SettlementRun,
)
from .services import get_or_create_organizer_payee

logger = logging.getLogger('finance.settlements')
ZERO = Decimal('0')


@transaction.atomic
def calculate_settlement(
    *,
    scope_type: str,
    scope_id: str,
    organizer,
    period_start: date,
    period_end: date,
    commercial_mode: str = 'collect_total',
    recognition_policy: str = 'on_settlement_close',
    settlement_policy: str = 'per_product',
    user=None,
) -> SettlementRun:
    """Create a draft SettlementRun with calculated lines from Orders and ExternalRevenueRecords."""

    settlement = SettlementRun.objects.create(
        scope_type=scope_type,
        scope_id=scope_id,
        organizer=organizer,
        commercial_mode=commercial_mode,
        recognition_policy=recognition_policy,
        settlement_policy=settlement_policy,
        period_start=period_start,
        period_end=period_end,
        settlement_date=timezone.localdate(),
        status='draft',
        currency='CLP',
        closed_by=user,
    )

    gross_total = ZERO
    fee_total = ZERO
    payable_total = ZERO

    order_filter = _build_order_filter(scope_type, scope_id, period_start, period_end)
    orders = Order.objects.filter(order_filter, order_revenue_eligible_q()).select_related(
        'event', 'experience_reservation__experience',
        'accommodation_reservation__accommodation',
    )

    for order in orders:
        subtotal = Decimal(str(order.subtotal_effective or order.subtotal or 0))
        service_fee = Decimal(str(order.service_fee_effective or order.service_fee or 0))
        payable = subtotal

        line = SettlementLine.objects.create(
            settlement_run=settlement,
            source_type=f'{order.order_kind}_order',
            source_id=order.id,
            order=order,
            gross_amount=subtotal + service_fee,
            platform_fee_amount=service_fee,
            payable_amount=payable,
            effective_date=order.created_at.date(),
            completion_date=_get_order_completion_date(order),
        )

        gross_total += line.gross_amount
        fee_total += line.platform_fee_amount
        payable_total += line.payable_amount

    ext_records = ExternalRevenueRecord.objects.filter(
        organizer=organizer,
        status='active',
        exclude_from_revenue=False,
        effective_date__gte=period_start,
        effective_date__lte=period_end,
    )

    for record in ext_records:
        line = SettlementLine.objects.create(
            settlement_run=settlement,
            source_type='external_revenue',
            source_id=record.id,
            external_revenue_record=record,
            gross_amount=record.gross_amount,
            platform_fee_amount=record.platform_fee_amount,
            payable_amount=record.payable_amount,
            effective_date=record.effective_date,
            completion_date=record.completion_date,
        )
        gross_total += line.gross_amount
        fee_total += line.platform_fee_amount
        payable_total += line.payable_amount

    settlement.gross_collected = gross_total
    settlement.platform_fee_recognized = fee_total
    settlement.payable_amount = payable_total
    settlement.status = 'calculated'
    settlement.save()

    logger.info(
        'Settlement %s calculated: scope=%s:%s gross=%s fee=%s payable=%s lines=%d',
        settlement.id, scope_type, scope_id,
        gross_total, fee_total, payable_total,
        settlement.lines.count(),
    )

    return settlement


def _build_order_filter(scope_type: str, scope_id: str, period_start: date, period_end: date) -> Q:
    base = Q(created_at__date__gte=period_start, created_at__date__lte=period_end)
    if scope_type == 'event':
        return base & Q(order_kind='event', event_id=scope_id)
    if scope_type == 'experience':
        return base & Q(order_kind='experience', experience_reservation__experience_id=scope_id)
    if scope_type == 'accommodation':
        return base & Q(order_kind='accommodation', accommodation_reservation__accommodation_id=scope_id)
    if scope_type == 'organizer':
        return base & (
            Q(event__organizer_id=scope_id)
            | Q(experience_reservation__experience__organizer_id=scope_id)
            | Q(accommodation_reservation__accommodation__organizer_id=scope_id)
        )
    return base


def _get_order_completion_date(order: Order):
    if order.completion_date:
        return order.completion_date.date() if hasattr(order.completion_date, 'date') else order.completion_date
    if order.order_kind == 'event' and order.event_id and order.event:
        end = order.event.end_date or order.event.start_date
        if end:
            return end.date() if hasattr(end, 'date') else end
    return None


@transaction.atomic
def post_settlement(settlement: SettlementRun, *, user=None) -> SettlementRun:
    """Move a calculated settlement to posted and create PayableLines."""
    if settlement.status != 'calculated':
        raise ValueError(f'Cannot post settlement in status {settlement.status}')

    payee = get_or_create_organizer_payee(settlement.organizer)

    for line in settlement.lines.all():
        if line.payable_amount <= ZERO:
            continue
        PayableLine.objects.update_or_create(
            source_reference=f'settlement:{settlement.id}:line:{line.id}',
            defaults={
                'payee': payee,
                'order': line.order,
                'external_revenue_record': line.external_revenue_record,
                'settlement_run': settlement,
                'source_type': line.source_type,
                'source_label': f'Settlement {settlement.scope_type}:{settlement.scope_id}',
                'status': 'open',
                'maturity_status': 'available',
                'gross_amount': line.gross_amount,
                'platform_fee_amount': line.platform_fee_amount,
                'payable_amount': line.payable_amount,
                'currency': settlement.currency,
                'commercial_mode': settlement.commercial_mode,
                'effective_at': timezone.now(),
                'due_date': settlement.settlement_date,
            },
        )

    settlement.status = 'posted'
    settlement.posting_date = timezone.localdate()
    settlement.closed_at = timezone.now()
    settlement.closed_by = user
    settlement.save()

    logger.info('Settlement %s posted by %s, payable_amount=%s', settlement.id, user, settlement.payable_amount)

    return settlement


@transaction.atomic
def void_settlement(settlement: SettlementRun) -> SettlementRun:
    """Void a draft or calculated settlement and clean up any payables."""
    if settlement.status not in ('draft', 'calculated'):
        raise ValueError(f'Cannot void settlement in status {settlement.status}')

    voided_count = PayableLine.objects.filter(
        settlement_run=settlement,
        status__in=('open', 'batched'),
    ).update(status='voided')

    settlement.status = 'voided'
    settlement.save(update_fields=['status', 'updated_at'])

    logger.info('Settlement %s voided, %d payable lines voided', settlement.id, voided_count)

    return settlement


def get_partner_custody_position(organizer) -> dict:
    """Calculate third-party funds position for a given organizer (modalidad 1 only)."""
    from .services import payout_totals_for_payee

    payee = PayeeAccount.objects.filter(
        organizer=organizer, actor_type='organizer',
    ).first()

    if not payee:
        return {
            'organizer_id': str(organizer.id),
            'organizer_name': organizer.name,
            'gross_collected': 0,
            'platform_fee': 0,
            'payable_total': 0,
            'paid_total': 0,
            'retained': 0,
        }

    lines = payee.payable_lines.exclude(status='voided')
    agg = lines.aggregate(
        gross=Sum('gross_amount'),
        fees=Sum('platform_fee_amount'),
        payable=Sum('payable_amount'),
    )
    paid = lines.filter(status__in=['paid', 'reconciled']).aggregate(
        total=Sum('payable_amount'),
    )['total'] or ZERO

    gross = agg['gross'] or ZERO
    fees = agg['fees'] or ZERO
    payable = agg['payable'] or ZERO

    return {
        'organizer_id': str(organizer.id),
        'organizer_name': organizer.name,
        'gross_collected': float(gross),
        'platform_fee': float(fees),
        'payable_total': float(payable),
        'paid_total': float(paid),
        'retained': float(payable - paid),
    }
