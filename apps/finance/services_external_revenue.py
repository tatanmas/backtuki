"""External revenue import and sync services.

Handles idempotent JSON import of historical/external revenue records,
and syncing them to PayableLines.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import (
    ExternalRevenueImportBatch,
    ExternalRevenueRecord,
    PayableLine,
    PayeeAccount,
)

logger = logging.getLogger('finance.external_revenue')
ZERO = Decimal('0')


def _checksum(payload: list[dict]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ZERO


def _parse_date(value: Any):
    """Parse date from string (YYYY-MM-DD) or return as-is if already date."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


@transaction.atomic
def import_external_revenue(
    *,
    payload: list[dict],
    source: str,
    uploaded_by=None,
    original_filename: str = '',
    dry_run: bool = False,
    skip_duplicates: bool = True,
) -> dict:
    """Import a list of external revenue records from JSON.

    Returns a summary dict with counts and batch id.
    """
    checksum = _checksum(payload)

    if not dry_run and ExternalRevenueImportBatch.objects.filter(
        payload_checksum=checksum, status='completed'
    ).exists():
        logger.info('Duplicate batch skipped (checksum=%s)', checksum[:16])
        return {
            'batch_id': None,
            'status': 'duplicate_batch',
            'records_received': len(payload),
            'records_created': 0,
            'records_skipped': len(payload),
            'records_failed': 0,
            'errors': [],
        }

    batch = ExternalRevenueImportBatch.objects.create(
        source=source,
        status='dry_run' if dry_run else 'processing',
        uploaded_by=uploaded_by,
        original_filename=original_filename,
        payload_checksum=checksum,
        records_received=len(payload),
    )

    created = 0
    skipped = 0
    failed = 0
    errors = []

    for idx, record_data in enumerate(payload):
        try:
            result = _process_single_record(record_data, batch, dry_run, skip_duplicates)
            if result == 'created':
                created += 1
            elif result == 'skipped':
                skipped += 1
        except Exception as exc:
            failed += 1
            errors.append({'index': idx, 'error': str(exc), 'data': record_data})

    batch.records_created = created
    batch.records_skipped = skipped
    batch.records_failed = failed
    batch.errors = errors
    batch.status = 'dry_run' if dry_run else ('completed' if failed == 0 else 'failed')
    batch.save()

    logger.info(
        'Import batch %s: status=%s created=%d skipped=%d failed=%d',
        batch.id, batch.status, created, skipped, failed,
    )

    return {
        'batch_id': str(batch.id),
        'status': batch.status,
        'records_received': len(payload),
        'records_created': created,
        'records_skipped': skipped,
        'records_failed': failed,
        'errors': errors,
    }


def _process_single_record(
    data: dict,
    batch: ExternalRevenueImportBatch,
    dry_run: bool,
    skip_duplicates: bool,
) -> str:
    source_type = data.get('source_type', 'manual')
    external_reference = data.get('external_reference', '')

    if not external_reference:
        raise ValueError('external_reference is required')

    exists = ExternalRevenueRecord.objects.filter(
        source_type=source_type,
        external_reference=external_reference,
        status='active',
    ).exists()

    if exists:
        if skip_duplicates:
            return 'skipped'
        raise ValueError(f'Duplicate: {source_type}:{external_reference}')

    if dry_run:
        return 'created'

    from apps.organizers.models import Organizer
    organizer = None
    organizer_id = data.get('organizer_id')
    if organizer_id:
        organizer = Organizer.objects.get(id=organizer_id)

    eff_date = _parse_date(data.get('effective_date'))
    if not eff_date:
        raise ValueError('effective_date is required')

    ExternalRevenueRecord.objects.create(
        import_batch=batch,
        source_type=source_type,
        source_system=data.get('source_system', ''),
        external_reference=external_reference,
        organizer=organizer,
        event_id=data.get('event_id') or None,
        experience_id=data.get('experience_id') or None,
        accommodation_id=data.get('accommodation_id') or None,
        car_id=data.get('car_id') or None,
        product_label=data.get('product_label', ''),
        commercial_mode=data.get('commercial_mode', 'collect_total'),
        gross_amount=_decimal(data.get('gross_amount', 0)),
        platform_fee_amount=_decimal(data.get('platform_fee_amount', 0)),
        payable_amount=_decimal(data.get('payable_amount', 0)),
        currency=data.get('currency', 'CLP'),
        effective_date=eff_date,
        service_date=_parse_date(data.get('service_date')) or None,
        completion_date=_parse_date(data.get('completion_date')) or None,
        settlement_date=_parse_date(data.get('settlement_date')) or None,
        posting_date=_parse_date(data.get('posting_date')) or None,
        due_date=_parse_date(data.get('due_date')) or None,
        description=data.get('description', ''),
        exclude_from_revenue=data.get('exclude_from_revenue', False),
        already_paid=data.get('already_paid', False),
        metadata=data.get('metadata', {}),
    )
    return 'created'


@transaction.atomic
def reverse_external_revenue_record(record: ExternalRevenueRecord, *, user=None) -> ExternalRevenueRecord:
    """Create a reversal record and void related payables."""
    if record.status != 'active':
        raise ValueError(f'Cannot reverse record in status {record.status}')

    reversal = ExternalRevenueRecord.objects.create(
        source_type=record.source_type,
        source_system=record.source_system,
        external_reference=f'{record.external_reference}:reversal',
        organizer=record.organizer,
        event=record.event,
        experience=record.experience,
        accommodation=record.accommodation,
        car=record.car,
        product_label=record.product_label,
        commercial_mode=record.commercial_mode,
        gross_amount=-record.gross_amount,
        platform_fee_amount=-record.platform_fee_amount,
        payable_amount=-record.payable_amount,
        currency=record.currency,
        effective_date=timezone.localdate(),
        description=f'Reversal of {record.external_reference}',
        status='active',
        reversal_of=record,
        metadata={'reversed_record_id': str(record.id)},
    )

    record.status = 'reversed'
    record.save(update_fields=['status', 'updated_at'])

    PayableLine.objects.filter(
        external_revenue_record=record,
        status__in=('open', 'batched'),
    ).update(status='voided')

    return reversal


@transaction.atomic
def sync_external_revenue_payables() -> int:
    """Create or update PayableLines for active ExternalRevenueRecords.
    Skips records with organizer=null (orphans). For already_paid=True, creates line with status='paid'.
    """
    from .services import get_or_create_organizer_payee

    count = 0
    records = ExternalRevenueRecord.objects.filter(
        status='active',
        exclude_from_revenue=False,
        commercial_mode='collect_total',
    ).select_related('organizer')

    for record in records:
        if not record.organizer_id:
            continue
        payee = get_or_create_organizer_payee(record.organizer)
        if record.already_paid:
            line_status = 'paid'
            paid_at = timezone.make_aware(
                datetime.combine(record.effective_date, datetime.min.time())
            ) if record.effective_date else timezone.now()
        else:
            line_status = 'open' if record.payable_amount > ZERO else 'voided'
            paid_at = None

        defaults = {
            'payee': payee,
            'external_revenue_record': record,
            'source_type': 'external_revenue',
            'source_label': record.product_label or record.external_reference,
            'status': line_status,
            'maturity_status': 'available',
            'gross_amount': record.gross_amount,
            'platform_fee_amount': record.platform_fee_amount,
            'payable_amount': record.payable_amount,
            'currency': record.currency,
            'commercial_mode': record.commercial_mode,
            'effective_at': timezone.now(),
            'due_date': record.due_date,
            'metadata': {
                'source_type': record.source_type,
                'external_reference': record.external_reference,
                'product_label': record.product_label,
            },
        }
        if paid_at is not None:
            defaults['paid_at'] = paid_at

        PayableLine.objects.update_or_create(
            source_reference=f'ext_rev:{record.id}:organizer',
            defaults=defaults,
        )
        count += 1

    return count
