"""Cancellation and refund endpoints for superadmin."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.events.models import Order
from apps.finance.models import Payout
from apps.finance.services_cancellations import (
    process_order_cancellation,
    process_payout_clawback,
)

from ..permissions import IsSuperUser

logger = logging.getLogger('finance.api.cancellations')


def _safe_decimal(value, default=Decimal('0')) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_cancel_order(request, order_id):
    """Process full cancellation of an order with financial impact."""
    order = get_object_or_404(
        Order.objects.select_related(
            'event__organizer',
            'experience_reservation__experience__organizer',
            'accommodation_reservation__accommodation__organizer',
        ),
        id=order_id,
    )

    cancellation_reason = request.data.get('cancellation_reason', '')
    if not cancellation_reason:
        return Response(
            {'success': False, 'message': 'cancellation_reason is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    refund_amount_raw = request.data.get('refund_amount')
    refund_amount = _safe_decimal(refund_amount_raw) if refund_amount_raw is not None else None
    processor_fee_loss = _safe_decimal(request.data.get('processor_fee_loss', 0))
    refund_responsibility = request.data.get('refund_responsibility', 'tuki')

    if refund_responsibility not in ('tuki', 'organizer'):
        return Response(
            {'success': False, 'message': 'refund_responsibility must be "tuki" or "organizer"'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        result = process_order_cancellation(
            order=order,
            cancellation_reason=cancellation_reason,
            refund_amount=refund_amount,
            processor_fee_loss=processor_fee_loss,
            refund_responsibility=refund_responsibility,
            user=request.user,
        )
    except Exception as exc:
        logger.exception('Error processing cancellation for order %s', order_id)
        return Response(
            {'success': False, 'message': f'Cancellation error: {exc}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        'success': True,
        'order_id': str(order.id),
        'order_number': order.order_number,
        **result,
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_payout_clawback(request, payout_id):
    """Process clawback of an already-paid payout."""
    payout = get_object_or_404(Payout.objects.select_related('payee'), id=payout_id)

    reason = request.data.get('reason', '')
    if not reason:
        return Response(
            {'success': False, 'message': 'reason is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        result = process_payout_clawback(
            payout=payout,
            reason=reason,
            user=request.user,
        )
    except ValueError as exc:
        return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception('Error processing payout clawback %s', payout_id)
        return Response(
            {'success': False, 'message': f'Clawback error: {exc}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({'success': True, **result})
