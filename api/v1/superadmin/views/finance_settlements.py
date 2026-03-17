"""Settlement and third-party funds endpoints for superadmin."""

from __future__ import annotations

import logging
from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.finance.models import SettlementRun
from apps.finance.services_settlements import (
    calculate_settlement,
    get_partner_custody_position,
    post_settlement,
    void_settlement,
)
from apps.organizers.models import Organizer

from ..permissions import IsSuperUser

logger = logging.getLogger('finance.api.settlements')


def _serialize_settlement(s: SettlementRun) -> dict:
    def _d(d):
        if d is None:
            return None
        return d.isoformat() if hasattr(d, 'isoformat') else str(d)[:10]

    return {
        'id': str(s.id),
        'scope_type': s.scope_type,
        'scope_id': str(s.scope_id) if s.scope_id else None,
        'organizer_id': str(s.organizer_id),
        'organizer_name': s.organizer.name if s.organizer else None,
        'commercial_mode': s.commercial_mode,
        'recognition_policy': s.recognition_policy,
        'settlement_policy': s.settlement_policy,
        'period_start': _d(s.period_start),
        'period_end': _d(s.period_end),
        'settlement_date': _d(s.settlement_date),
        'posting_date': _d(s.posting_date),
        'status': s.status,
        'gross_collected': float(s.gross_collected),
        'platform_fee_recognized': float(s.platform_fee_recognized),
        'payable_amount': float(s.payable_amount),
        'currency': s.currency,
        'lines_count': s.lines.count(),
        'created_at': s.created_at.isoformat() if s.created_at else None,
        'closed_at': s.closed_at.isoformat() if s.closed_at else None,
    }


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_settlements_list(request):
    """List settlement runs."""
    qs = SettlementRun.objects.select_related('organizer').order_by('-settlement_date', '-created_at')

    organizer_id = request.query_params.get('organizer_id')
    if organizer_id:
        qs = qs.filter(organizer_id=organizer_id)

    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    results = [_serialize_settlement(s) for s in qs[:200]]
    return Response({'success': True, 'results': results, 'count': len(results)})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_settlements_calculate(request):
    """Calculate a new settlement."""
    required = ['scope_type', 'scope_id', 'organizer_id', 'period_start', 'period_end']
    missing = [f for f in required if not request.data.get(f)]
    if missing:
        return Response(
            {'success': False, 'message': f'Missing fields: {", ".join(missing)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    organizer = get_object_or_404(Organizer, id=request.data['organizer_id'])

    def _parse_d(s):
        if s is None:
            return None
        if isinstance(s, date):
            return s
        return date.fromisoformat(str(s)[:10])

    try:
        settlement = calculate_settlement(
            scope_type=request.data['scope_type'],
            scope_id=str(request.data['scope_id']),
            organizer=organizer,
            period_start=_parse_d(request.data['period_start']),
            period_end=_parse_d(request.data['period_end']),
            commercial_mode=request.data.get('commercial_mode', 'collect_total'),
            recognition_policy=request.data.get('recognition_policy', 'on_settlement_close'),
            settlement_policy=request.data.get('settlement_policy', 'per_product'),
            user=request.user,
        )
    except Exception as exc:
        return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({'success': True, 'settlement': _serialize_settlement(settlement)})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_settlement_post(request, settlement_id):
    """Post a calculated settlement (creates PayableLines)."""
    settlement = get_object_or_404(SettlementRun.objects.select_related('organizer'), id=settlement_id)
    try:
        settlement = post_settlement(settlement, user=request.user)
    except ValueError as exc:
        return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'success': True, 'settlement': _serialize_settlement(settlement)})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_settlement_void(request, settlement_id):
    """Void a draft or calculated settlement."""
    settlement = get_object_or_404(SettlementRun, id=settlement_id)
    try:
        settlement = void_settlement(settlement)
    except ValueError as exc:
        return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'success': True, 'settlement': _serialize_settlement(settlement)})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_third_party_funds(request):
    """Get third-party funds (custody position) for all organizers or a specific one."""
    organizer_id = request.query_params.get('organizer_id')

    if organizer_id:
        organizer = get_object_or_404(Organizer, id=organizer_id)
        position = get_partner_custody_position(organizer)
        return Response({'success': True, 'positions': [position]})

    organizers = Organizer.objects.filter(status='active')
    positions = []
    for org in organizers:
        pos = get_partner_custody_position(org)
        if pos['gross_collected'] > 0 or pos['retained'] > 0:
            positions.append(pos)

    positions.sort(key=lambda p: p['retained'], reverse=True)
    return Response({'success': True, 'positions': positions, 'count': len(positions)})
