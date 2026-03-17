"""Generic bank export builders and adapters."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from django.utils import timezone

from .models import BankExportFile, Payout


def _to_int_amount(value: Decimal) -> int:
    return int(round(float(value or 0)))


def build_generic_rows(payouts):
    rows = []
    for payout in payouts.select_related('payee'):
        payee = payout.payee
        rows.append({
            'payout_id': str(payout.id),
            'payee_id': str(payee.id),
            'actor_type': payee.actor_type,
            'display_name': payee.display_name,
            'tax_name': payee.tax_name,
            'tax_id': payee.tax_id,
            'bank_name': payee.bank_name,
            'account_type': payee.account_type,
            'account_number': payee.account_number,
            'account_holder': payee.account_holder,
            'recipient_type': payee.recipient_type,
            'document_type': payee.document_type,
            'document_number': payee.document_number,
            'country_code': payee.country_code,
            'amount': _to_int_amount(payout.amount),
            'currency': payout.currency,
            'reference': payout.reference,
            'bank_reference': payout.bank_reference,
        })
    return rows


def build_generic_preview(payouts):
    rows = build_generic_rows(payouts)
    totals = {
        'rows': len(rows),
        'amount': sum(row['amount'] for row in rows),
        'currency': rows[0]['currency'] if rows else 'CLP',
    }
    return {'adapter_code': 'generic_cl_payroll_v1', 'rows': rows, 'totals': totals}


def create_bank_export_file(*, payouts, user=None, batch=None, adapter_code='generic_cl_payroll_v1'):
    preview = build_generic_preview(payouts)
    payload = {
        'generated_at': timezone.now().isoformat(),
        'adapter_code': adapter_code,
        'rows': preview['rows'],
        'totals': preview['totals'],
    }
    checksum = hashlib.sha256(str(payload).encode('utf-8')).hexdigest()
    filename = f'finance_export_{timezone.localdate().isoformat()}.json'
    return BankExportFile.objects.create(
        batch=batch,
        adapter_code=adapter_code,
        filename=filename,
        checksum=checksum,
        content=preview['rows'],
        row_count=len(preview['rows']),
        generated_by=user,
    )


def get_exportable_payouts_for_batch(batch):
    return Payout.objects.filter(batch=batch, status__in=['approved', 'exported', 'submitted', 'paid']).select_related('payee')
