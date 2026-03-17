"""Services for syncing payables and computing finance summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.creators.models import CreatorProfile
from apps.events.models import Order
from apps.experiences.models import ExperienceReservation
from core.revenue_system import order_revenue_eligible_q
from apps.organizers.bank_constants import PERSON_TYPE_TO_RECIPIENT
from apps.organizers.models import Organizer

from .models import FinancePlatformSettings, PayableLine, PayeeAccount, PayeeSchedule, Payout, PayoutBatch, PayoutLineAllocation


ZERO = Decimal('0')


@dataclass
class OrganizerOrderPayableData:
    payable_amount: Decimal
    gross_amount: Decimal
    platform_fee_amount: Decimal
    due_date: object
    source_label: str
    metadata: dict


def _decimal(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _safe_date(value):
    if value is None:
        return None
    if hasattr(value, 'date'):
        try:
            return value.date()
        except Exception:
            return value
    return value


def get_finance_platform_settings() -> FinancePlatformSettings:
    settings = FinancePlatformSettings.objects.order_by('created_at').first()
    if settings:
        return settings
    return FinancePlatformSettings.objects.create()


def get_or_create_organizer_payee(organizer: Organizer) -> PayeeAccount:
    defaults = {
        'actor_type': 'organizer',
        'actor_id': organizer.id,
        'display_name': organizer.name,
        'legal_name': organizer.name,
        'email': organizer.contact_email or '',
        'organizer': organizer,
    }
    payee, _ = PayeeAccount.objects.get_or_create(
        account_key=f'organizer:{organizer.id}',
        defaults=defaults,
    )
    changed = False
    for field, value in defaults.items():
        if getattr(payee, field) != value:
            setattr(payee, field, value)
            changed = True

    try:
        banking = organizer.banking_details
    except Exception:
        banking = None
    try:
        billing = organizer.billing_details
    except Exception:
        billing = None

    if banking:
        bank_updates = {
            'bank_name': banking.bank_name or '',
            'account_type': banking.account_type or '',
            'account_number': banking.account_number or '',
            'account_holder': banking.account_holder or '',
        }
        for field, value in bank_updates.items():
            if getattr(payee, field) != value:
                setattr(payee, field, value)
                changed = True
    if billing:
        billing_updates = {
            'person_type': billing.person_type or '',
            'tax_name': billing.tax_name or '',
            'tax_id': billing.tax_id or '',
            'document_number': billing.tax_id or '',
            'billing_address': billing.billing_address or '',
            'recipient_type': PERSON_TYPE_TO_RECIPIENT.get(billing.person_type, ''),
        }
        for field, value in billing_updates.items():
            if getattr(payee, field) != value:
                setattr(payee, field, value)
                changed = True

    if changed:
        payee.save()
    PayeeSchedule.objects.get_or_create(payee=payee)
    return payee


def get_or_create_creator_payee(creator: CreatorProfile) -> PayeeAccount:
    bank = creator.bank_details or {}
    defaults = {
        'actor_type': 'creator',
        'actor_id': creator.id,
        'display_name': creator.display_name,
        'legal_name': creator.display_name,
        'email': creator.user.email if creator.user_id else '',
        'phone': creator.phone or '',
        'creator': creator,
        'bank_name': bank.get('bank_name', '') or '',
        'account_type': bank.get('account_type', '') or '',
        'account_number': bank.get('account_number', '') or '',
        'account_holder': bank.get('holder_name', '') or bank.get('account_holder', '') or creator.display_name,
        'tax_id': bank.get('rut', '') or '',
        'document_number': bank.get('rut', '') or '',
        'tax_name': creator.display_name,
        'recipient_type': 'Persona',
    }
    payee, _ = PayeeAccount.objects.get_or_create(
        account_key=f'creator:{creator.id}',
        defaults=defaults,
    )
    changed = False
    for field, value in defaults.items():
        if getattr(payee, field) != value:
            setattr(payee, field, value)
            changed = True
    if changed:
        payee.save()
    PayeeSchedule.objects.get_or_create(payee=payee)
    return payee


def _get_order_organizer(order: Order):
    if order.order_kind == 'event' and order.event_id and order.event and order.event.organizer_id:
        return order.event.organizer
    if order.order_kind == 'experience' and order.experience_reservation_id and order.experience_reservation and order.experience_reservation.experience_id:
        return order.experience_reservation.experience.organizer
    if order.order_kind == 'accommodation' and order.accommodation_reservation_id and order.accommodation_reservation and order.accommodation_reservation.accommodation_id:
        return order.accommodation_reservation.accommodation.organizer
    if order.order_kind == 'car_rental' and order.car_rental_reservation_id and order.car_rental_reservation and order.car_rental_reservation.car_id:
        company = order.car_rental_reservation.car.company
        return company.organizer
    return None


def _get_effective_order_amounts(order: Order):
    subtotal = _decimal(order.subtotal_effective or order.subtotal)
    service_fee = _decimal(order.service_fee_effective or order.service_fee)
    return subtotal, service_fee


def _get_accommodation_payment_model(order: Order) -> str:
    reservation = order.accommodation_reservation
    if not reservation or not reservation.accommodation_id:
        return 'full_platform'
    accommodation = reservation.accommodation
    if accommodation.payment_model:
        return accommodation.payment_model
    if accommodation.hotel_id and accommodation.hotel and accommodation.hotel.payment_model:
        return accommodation.hotel.payment_model
    return 'full_platform'


def compute_organizer_payable_for_order(order: Order) -> OrganizerOrderPayableData | None:
    organizer = _get_order_organizer(order)
    if organizer is None:
        return None

    subtotal, service_fee = _get_effective_order_amounts(order)
    due_date = None
    payable_amount = subtotal
    metadata = {
        'order_kind': order.order_kind,
        'order_id': str(order.id),
        'order_number': order.order_number,
        'buyer_name': order.buyer_name,
        'is_sandbox': bool(order.is_sandbox),
        'exclude_from_revenue': bool(getattr(order, 'exclude_from_revenue', False)),
        'counts_for_revenue': bool(getattr(order, 'counts_for_revenue', False)),
    }

    if order.order_kind == 'event' and order.event_id and order.event:
        due_date = _safe_date(order.event.end_date or order.event.start_date or order.created_at)
        source_label = order.event.title
        metadata.update({
            'group_type': 'event',
            'group_id': str(order.event_id),
            'group_label': order.event.title,
            'ticket_quantity': sum((item.quantity for item in order.items.all()), 0),
        })
    elif order.order_kind == 'experience' and order.experience_reservation_id and order.experience_reservation:
        reservation = order.experience_reservation
        experience = reservation.experience
        payment_model = getattr(experience, 'payment_model', 'full_upfront')
        metadata['payment_model'] = payment_model
        due_date = _safe_date(
            reservation.attended_at
            or (reservation.instance.start_datetime if reservation.instance_id and reservation.instance else None)
            or reservation.paid_at
            or order.created_at
        )
        source_label = experience.title
        metadata.update({
            'group_type': 'experience',
            'group_id': str(experience.id) if experience else None,
            'group_label': experience.title,
        })
        if payment_model == 'deposit_only':
            payable_amount = ZERO
    elif order.order_kind == 'accommodation' and order.accommodation_reservation_id and order.accommodation_reservation:
        reservation = order.accommodation_reservation
        payment_model = _get_accommodation_payment_model(order)
        metadata['payment_model'] = payment_model
        due_date = _safe_date(reservation.check_out or reservation.paid_at or order.created_at)
        source_label = reservation.accommodation.title if reservation.accommodation_id else order.order_number
        metadata.update({
            'group_type': 'accommodation',
            'group_id': str(reservation.accommodation_id) if reservation.accommodation_id else None,
            'group_label': source_label,
        })
        if payment_model == 'commission_only':
            payable_amount = ZERO
    elif order.order_kind == 'car_rental' and order.car_rental_reservation_id and order.car_rental_reservation:
        reservation = order.car_rental_reservation
        due_date = _safe_date(reservation.return_date or reservation.pickup_date or reservation.paid_at or order.created_at)
        source_label = reservation.car.title if reservation.car_id else order.order_number
        metadata.update({
            'group_type': 'car_rental',
            'group_id': str(reservation.car_id) if reservation.car_id else None,
            'group_label': source_label,
        })
    elif order.order_kind == 'erasmus_activity':
        due_date = _safe_date(order.created_at)
        source_label = order.order_number
    else:
        source_label = order.order_number

    return OrganizerOrderPayableData(
        payable_amount=payable_amount,
        gross_amount=subtotal,
        platform_fee_amount=service_fee,
        due_date=due_date,
        source_label=source_label,
        metadata=metadata,
    )


@transaction.atomic
def sync_organizer_payables() -> int:
    count = 0
    orders = (
        Order.objects.filter(order_revenue_eligible_q())
        .select_related(
            'event__organizer',
            'experience_reservation__experience__organizer',
            'experience_reservation__instance',
            'accommodation_reservation__accommodation__organizer',
            'accommodation_reservation__accommodation__hotel',
            'car_rental_reservation__car__company__organizer',
        )
        .prefetch_related('items')
    )
    for order in orders:
        organizer = _get_order_organizer(order)
        if organizer is None:
            continue
        payee = get_or_create_organizer_payee(organizer)
        payable = compute_organizer_payable_for_order(order)
        if payable is None:
            continue
        status = 'open'
        if payable.payable_amount <= ZERO:
            status = 'voided'
        defaults = {
            'payee': payee,
            'order': order,
            'source_type': f'{order.order_kind}_order',
            'source_label': payable.source_label,
            'status': status,
            'maturity_status': 'available',
            'gross_amount': payable.gross_amount,
            'platform_fee_amount': payable.platform_fee_amount,
            'payable_amount': payable.payable_amount,
            'currency': 'CLP',
            'effective_at': order.created_at,
            'due_date': payable.due_date,
            'metadata': payable.metadata,
        }
        PayableLine.objects.update_or_create(
            source_reference=f'order:{order.id}:organizer',
            defaults=defaults,
        )
        count += 1
    return count


def void_organizer_payable_for_order(order: Order) -> int:
    """
    When an order is marked exclude_from_revenue=True, void its organizer PayableLine
    so it no longer counts toward payouts. Returns the number of lines updated (0 or 1).
    """
    updated = PayableLine.objects.filter(
        source_reference=f'order:{order.id}:organizer',
        status__in=('open', 'batched'),
    ).update(status='voided')
    return updated


def ensure_organizer_payable_for_order(order: Order) -> bool:
    """
    When an order is set exclude_from_revenue=False (included again), create or update
    its organizer PayableLine so it counts toward payouts. Returns True if a line was
    created or updated. Call this after un-excluding an order so payables are correct
    without waiting for sync_organizer_payables().
    """
    if (
        order.status != 'paid'
        or order.is_sandbox
        or order.deleted_at is not None
        or order.exclude_from_revenue
    ):
        return False
    organizer = _get_order_organizer(order)
    if organizer is None:
        return False
    payee = get_or_create_organizer_payee(organizer)
    payable = compute_organizer_payable_for_order(order)
    if payable is None:
        return False
    line_status = 'open' if payable.payable_amount > ZERO else 'voided'
    defaults = {
        'payee': payee,
        'order': order,
        'source_type': f'{order.order_kind}_order',
        'source_label': payable.source_label,
        'status': line_status,
        'maturity_status': 'available',
        'gross_amount': payable.gross_amount,
        'platform_fee_amount': payable.platform_fee_amount,
        'payable_amount': payable.payable_amount,
        'currency': 'CLP',
        'effective_at': order.created_at,
        'due_date': payable.due_date,
        'metadata': payable.metadata,
    }
    PayableLine.objects.update_or_create(
        source_reference=f'order:{order.id}:organizer',
        defaults=defaults,
    )
    return True


@transaction.atomic
def sync_creator_payables() -> int:
    count = 0
    reservations = (
        ExperienceReservation.objects.filter(
            creator__isnull=False,
            status='paid',
            creator_commission_amount__gt=0,
        )
        .select_related('creator__user', 'experience', 'instance')
    )
    for reservation in reservations:
        payee = get_or_create_creator_payee(reservation.creator)
        maturity = 'pending' if reservation.creator_commission_status == 'pending' else 'available'
        line_status = 'paid' if reservation.creator_commission_status == 'paid' else 'open'
        if reservation.creator_commission_status == 'reversed':
            line_status = 'voided'
        due_date = _safe_date(
            reservation.attended_at
            or (reservation.instance.start_datetime if reservation.instance_id and reservation.instance else None)
            or reservation.paid_at
            or reservation.created_at
        )
        PayableLine.objects.update_or_create(
            source_reference=f'reservation:{reservation.id}:creator',
            defaults={
                'payee': payee,
                'experience_reservation': reservation,
                'source_type': 'creator_commission',
                'source_label': reservation.experience.title if reservation.experience_id else reservation.reservation_id,
                'status': line_status,
                'maturity_status': maturity,
                'gross_amount': _decimal(reservation.total),
                'platform_fee_amount': ZERO,
                'payable_amount': _decimal(reservation.creator_commission_amount),
                'currency': reservation.currency or 'CLP',
                'effective_at': reservation.paid_at or reservation.created_at,
                'due_date': due_date,
                'paid_at': reservation.paid_at if reservation.creator_commission_status == 'paid' else None,
                'metadata': {
                    'creator_commission_status': reservation.creator_commission_status,
                },
            },
        )
        count += 1
    return count


def sync_all_payables() -> dict:
    return {
        'organizer_lines_synced': sync_organizer_payables(),
        'creator_lines_synced': sync_creator_payables(),
    }


def payout_totals_for_payee(payee: PayeeAccount) -> dict:
    lines = payee.payable_lines.exclude(status='voided')
    open_lines = lines.filter(status='open', maturity_status='available')
    pending_lines = lines.filter(status='open', maturity_status='pending')
    paid_lines = lines.filter(status__in=['paid', 'reconciled'])
    payouts = payee.payouts.filter(status__in=['paid', 'reconciled'])
    return {
        'gross_sales': float(lines.aggregate(total=Sum('gross_amount'))['total'] or ZERO),
        'platform_fees': float(lines.aggregate(total=Sum('platform_fee_amount'))['total'] or ZERO),
        'pending_amount': float(open_lines.aggregate(total=Sum('payable_amount'))['total'] or ZERO),
        'pending_future_amount': float(pending_lines.aggregate(total=Sum('payable_amount'))['total'] or ZERO),
        'paid_amount': float(paid_lines.aggregate(total=Sum('payable_amount'))['total'] or ZERO),
        'payouts_amount': float(payouts.aggregate(total=Sum('amount'))['total'] or ZERO),
        'lines_count': lines.count(),
    }


def create_payout_from_lines(*, payee: PayeeAccount, line_ids: list[str], amount: Decimal | None = None, reference: str = '', partner_message: str = '', user=None):
    lines = list(
        payee.payable_lines.filter(
            id__in=line_ids,
            status='open',
            maturity_status='available',
        ).order_by('effective_at', 'created_at')
    )
    if not lines:
        raise ValueError('No hay líneas pagables disponibles para este pago.')
    total_amount = sum((_decimal(line.payable_amount) for line in lines), ZERO)
    if amount is not None and _decimal(amount) != total_amount:
        raise ValueError('El monto debe coincidir con la suma de las líneas seleccionadas.')
    payout = Payout.objects.create(
        payee=payee,
        amount=total_amount,
        currency=payee.currency,
        status='paid',
        reference=reference,
        partner_message=partner_message,
        approved_by=user,
        paid_at=timezone.now(),
    )
    for line in lines:
        PayoutLineAllocation.objects.create(
            payout=payout,
            payable_line=line,
            amount=line.payable_amount,
        )
        line.status = 'paid'
        line.paid_at = payout.paid_at
        line.save(update_fields=['status', 'paid_at', 'updated_at'])

    if payee.actor_type == 'creator' and payee.creator_id:
        ExperienceReservation.objects.filter(
            id__in=[line.experience_reservation_id for line in lines if line.experience_reservation_id]
        ).update(creator_commission_status='paid')
    return payout


def build_default_batch_name() -> str:
    return f"Nómina {timezone.localdate().isoformat()}"


def set_next_payment_dates(days: int = 7):
    settings = get_finance_platform_settings()
    next_date = settings.default_next_payment_date or (timezone.localdate() + timedelta(days=days))
    PayeeSchedule.objects.filter(next_payment_date__isnull=True).update(next_payment_date=next_date)
