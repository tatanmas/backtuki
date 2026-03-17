"""Ledger and journal entry endpoints for superadmin."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.finance.models import JournalEntry, JournalLine, LedgerAccount

from ..permissions import IsSuperUser


def _serialize_entry(entry: JournalEntry) -> dict:
    return {
        'id': str(entry.id),
        'entry_date': entry.entry_date.isoformat(),
        'posting_date': entry.posting_date.isoformat(),
        'reference': entry.reference,
        'source_type': entry.source_type,
        'source_id': str(entry.source_id) if entry.source_id else None,
        'posting_event': entry.posting_event,
        'idempotency_key': entry.idempotency_key,
        'description': entry.description,
        'status': entry.status,
        'is_balanced': entry.is_balanced,
        'reversal_of_id': str(entry.reversal_of_id) if entry.reversal_of_id else None,
        'created_at': entry.created_at.isoformat() if entry.created_at else None,
    }


def _serialize_line(line: JournalLine) -> dict:
    return {
        'id': str(line.id),
        'account_code': line.ledger_account.code,
        'account_name': line.ledger_account.name,
        'debit_amount': float(line.debit_amount),
        'credit_amount': float(line.credit_amount),
        'currency': line.currency,
        'functional_amount': float(line.functional_amount),
        'description': line.description,
        'order_id': str(line.order_id) if line.order_id else None,
        'organizer_id': str(line.organizer_id) if line.organizer_id else None,
        'vendor_id': str(line.vendor_id) if line.vendor_id else None,
    }


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_ledger_accounts(request):
    """List all ledger accounts."""
    accounts = LedgerAccount.objects.filter(is_active=True).order_by('code')
    return Response({
        'success': True,
        'results': [
            {
                'id': str(a.id),
                'code': a.code,
                'name': a.name,
                'account_type': a.account_type,
                'subtype': a.subtype,
                'parent_id': str(a.parent_id) if a.parent_id else None,
            }
            for a in accounts
        ],
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_ledger_journal(request):
    """List journal entries with optional filters."""
    qs = JournalEntry.objects.order_by('-posting_date', '-created_at')

    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    source_type = request.query_params.get('source_type')
    if source_type:
        qs = qs.filter(source_type=source_type)

    posting_event = request.query_params.get('posting_event')
    if posting_event:
        qs = qs.filter(posting_event=posting_event)

    results = [_serialize_entry(e) for e in qs[:200]]
    return Response({'success': True, 'results': results, 'count': len(results)})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_ledger_journal_detail(request, entry_id):
    """Get a journal entry with all its lines."""
    entry = get_object_or_404(
        JournalEntry.objects.prefetch_related('lines__ledger_account'),
        id=entry_id,
    )
    return Response({
        'success': True,
        'entry': {
            **_serialize_entry(entry),
            'lines': [_serialize_line(line) for line in entry.lines.all()],
        },
    })
