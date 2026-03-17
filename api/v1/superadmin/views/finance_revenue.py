"""External revenue and revenue insights endpoints for superadmin."""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from apps.events.models import Order
from apps.finance.models import ExternalRevenueImportBatch, ExternalRevenueRecord, FinancialDocument
from apps.finance.services_external_revenue import (
    import_external_revenue,
    reverse_external_revenue_record,
    sync_external_revenue_payables,
)
from core.revenue_system import order_revenue_eligible_q

from ..permissions import IsSuperUser

logger = logging.getLogger('finance.api.revenue')
ZERO = Decimal('0')


def _serialize_record(record: ExternalRevenueRecord) -> dict:
    return {
        'id': str(record.id),
        'source_type': record.source_type,
        'source_system': record.source_system,
        'external_reference': record.external_reference,
        'organizer_id': str(record.organizer_id) if record.organizer_id else None,
        'organizer_name': record.organizer.name if record.organizer else None,
        'already_paid': getattr(record, 'already_paid', False),
        'product_label': record.product_label,
        'commercial_mode': record.commercial_mode,
        'gross_amount': float(record.gross_amount),
        'platform_fee_amount': float(record.platform_fee_amount),
        'payable_amount': float(record.payable_amount),
        'currency': record.currency,
        'effective_date': record.effective_date.isoformat() if record.effective_date else None,
        'service_date': record.service_date.isoformat() if record.service_date else None,
        'status': record.status,
        'exclude_from_revenue': record.exclude_from_revenue,
        'description': record.description,
        'created_at': record.created_at.isoformat() if record.created_at else None,
    }


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_external_revenue_import(request):
    """Import external revenue records from JSON payload."""
    payload = request.data.get('records') or request.data.get('leads') or []
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning('Invalid JSON in external revenue import: %s', exc)
            return Response(
                {'success': False, 'message': f'Invalid JSON: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
    if not payload:
        return Response(
            {'success': False, 'message': 'No records provided'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        result = import_external_revenue(
            payload=payload,
            source=request.data.get('source', 'superadmin'),
            uploaded_by=request.user,
            original_filename=request.data.get('filename', ''),
            dry_run=request.data.get('dry_run', False),
            skip_duplicates=request.data.get('skip_duplicates', True),
        )
    except Exception as exc:
        logger.exception('Unexpected error during external revenue import')
        return Response(
            {'success': False, 'message': f'Import error: {exc}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response({'success': True, **result})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_external_revenue_list(request):
    """List external revenue records with optional filters."""
    qs = ExternalRevenueRecord.objects.select_related('organizer').order_by('-effective_date', '-created_at')

    organizer_id = request.query_params.get('organizer_id')
    if organizer_id:
        qs = qs.filter(organizer_id=organizer_id)

    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    else:
        qs = qs.exclude(status='voided')

    results = [_serialize_record(r) for r in qs[:500]]
    return Response({'success': True, 'results': results, 'count': len(results)})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_external_revenue_detail(request, record_id):
    """Get a single external revenue record."""
    record = get_object_or_404(ExternalRevenueRecord.objects.select_related('organizer'), id=record_id)
    return Response({'success': True, 'record': _serialize_record(record)})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_external_revenue_exclude(request, record_id):
    """Toggle exclude_from_revenue on an external revenue record."""
    record = get_object_or_404(ExternalRevenueRecord, id=record_id)
    exclude = request.data.get('exclude', not record.exclude_from_revenue)
    record.exclude_from_revenue = exclude
    record.save(update_fields=['exclude_from_revenue', 'updated_at'])
    return Response({'success': True, 'exclude_from_revenue': record.exclude_from_revenue})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_external_revenue_reverse(request, record_id):
    """Reverse an external revenue record."""
    record = get_object_or_404(ExternalRevenueRecord, id=record_id)
    try:
        reversal = reverse_external_revenue_record(record, user=request.user)
    except ValueError as exc:
        return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'success': True, 'reversal': _serialize_record(reversal)})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_revenue_insights(request):
    """Operational revenue insights combining orders and external revenue."""
    period_start = request.query_params.get('period_start')
    period_end = request.query_params.get('period_end')

    order_q = order_revenue_eligible_q()
    if period_start:
        order_q &= Q(created_at__date__gte=period_start)
    if period_end:
        order_q &= Q(created_at__date__lte=period_end)

    order_agg = Order.objects.filter(order_q).aggregate(
        total_gross=Sum('total'),
        total_subtotal=Sum('subtotal_effective'),
        total_service_fee=Sum('service_fee_effective'),
    )
    order_count = Order.objects.filter(order_q).count()

    ext_q = Q(status='active', exclude_from_revenue=False)
    if period_start:
        ext_q &= Q(effective_date__gte=period_start)
    if period_end:
        ext_q &= Q(effective_date__lte=period_end)

    ext_agg = ExternalRevenueRecord.objects.filter(ext_q).aggregate(
        total_gross=Sum('gross_amount'),
        total_fee=Sum('platform_fee_amount'),
        total_payable=Sum('payable_amount'),
    )
    ext_count = ExternalRevenueRecord.objects.filter(ext_q).count()

    return Response({
        'success': True,
        'period_start': period_start,
        'period_end': period_end,
        'platform_orders': {
            'count': order_count,
            'gross_collected': float(order_agg['total_gross'] or 0),
            'organizer_revenue': float(order_agg['total_subtotal'] or 0),
            'platform_fee': float(order_agg['total_service_fee'] or 0),
        },
        'external_revenue': {
            'count': ext_count,
            'gross_amount': float(ext_agg['total_gross'] or 0),
            'platform_fee': float(ext_agg['total_fee'] or 0),
            'payable_amount': float(ext_agg['total_payable'] or 0),
        },
    })


@api_view(['POST', 'GET'])
@permission_classes([IsSuperUser])
@parser_classes([MultiPartParser, FormParser])
def finance_documents(request):
    """Upload or list financial documents."""
    if request.method == 'POST':
        file = request.FILES.get('file')
        if not file:
            return Response({'success': False, 'message': 'file is required'}, status=status.HTTP_400_BAD_REQUEST)
        doc = FinancialDocument.objects.create(
            doc_type=request.data.get('doc_type', 'support'),
            file=file,
            original_name=file.name,
            label=request.data.get('label', ''),
            external_revenue_record_id=request.data.get('external_revenue_record_id') or None,
            settlement_run_id=request.data.get('settlement_run_id') or None,
            event_id=request.data.get('event_id') or None,
            uploaded_by=request.user,
        )
        return Response({
            'success': True,
            'document': {
                'id': str(doc.id),
                'doc_type': doc.doc_type,
                'label': doc.label,
                'original_name': doc.original_name,
                'file_url': doc.file.url if doc.file else None,
            },
        })

    docs = FinancialDocument.objects.order_by('-created_at')[:200]
    return Response({
        'success': True,
        'results': [
            {
                'id': str(d.id),
                'doc_type': d.doc_type,
                'label': d.label,
                'original_name': d.original_name,
                'file_url': d.file.url if d.file else None,
                'created_at': d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
    })
