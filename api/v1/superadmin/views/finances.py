"""
SuperAdmin Finances Views

Enterprise organizer wallet: balance = revenue - organizer_credits - payouts.
Revenue = paid orders (events, experiences, accommodations).
OrganizerCredits = free tours (organizer pays platform).
"""

import io
import logging
from decimal import Decimal
from django.db.models import Sum, Q
from django.utils import timezone
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from django.core.exceptions import ObjectDoesNotExist

from apps.events.models import Order
from apps.organizers.models import Organizer, Payout
from core.revenue_system import order_revenue_eligible_q
from apps.organizers.wallet_service import get_organizer_wallet
from apps.organizers.bank_constants import (
    CHILE_BANK_CHOICES,
    CHILE_ACCOUNT_TYPES,
    CHILE_DOCUMENT_TYPES,
    RECIPIENT_TYPES,
    PERSON_TYPE_TO_RECIPIENT,
    DEFAULT_COUNTRY_CODE,
)

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def pending_payouts(request):
    """
    GET /api/v1/superadmin/pending-payouts/

    Returns organizers with wallet balance. Default: balance > 0 (we owe them).
    Query params: include_zero=1, include_negative=1 for full view.

    balance = revenue (events+exp+acc) - organizer_credits - payouts
    """
    try:
        include_zero = request.query_params.get('include_zero', '0') == '1'
        include_negative = request.query_params.get('include_negative', '0') == '1'

        organizers = Organizer.objects.prefetch_related(
            'banking_details', 'billing_details', 'payouts', 'credits'
        ).all()

        result = []
        for org in organizers:
            wallet = get_organizer_wallet(org)
            balance = wallet['balance']
            if balance > 0:
                pass
            elif balance == 0 and not include_zero:
                continue
            elif balance < 0 and not include_negative:
                continue

            last_order = Order.objects.filter(
                Q(event__organizer=org) |
                Q(experience_reservation__experience__organizer=org) |
                Q(accommodation_reservation__accommodation__organizer=org)
            ).filter(order_revenue_eligible_q()).order_by('-created_at').first()

            orders_count = Order.objects.filter(
                Q(event__organizer=org) |
                Q(experience_reservation__experience__organizer=org) |
                Q(accommodation_reservation__accommodation__organizer=org)
            ).filter(order_revenue_eligible_q()).count()

            try:
                banking = org.banking_details
            except ObjectDoesNotExist:
                banking = None
            try:
                billing = org.billing_details
            except ObjectDoesNotExist:
                billing = None
            has_banking = banking is not None
            has_billing = billing is not None
            can_export = has_banking and has_billing and balance > 0

            result.append({
                'organizer_id': str(org.id),
                'organizer_name': org.name,
                'organizer_email': org.contact_email,
                'total_revenue': wallet['total_revenue'],
                'organizer_credits': wallet['organizer_credits'],
                'payouts_sum': wallet['payouts_sum'],
                'balance': round(balance, 2),
                'pending': round(max(0, balance), 2),
                'by_type': wallet['by_type'],
                'breakdown': wallet.get('breakdown', {}),
                'orders_count': orders_count,
                'last_order_date': last_order.created_at.isoformat() if last_order else None,
                'has_banking_details': has_banking,
                'has_billing_details': has_billing,
                'can_export': can_export,
                'banking_details': {
                    'bank_name': banking.bank_name if banking else None,
                    'account_type': banking.account_type if banking else None,
                    'account_number': banking.account_number if banking else None,
                    'account_holder': banking.account_holder if banking else None,
                } if banking else None,
                'billing_details': {
                    'tax_id': billing.tax_id if billing else None,
                    'tax_name': billing.tax_name if billing else None,
                    'person_type': billing.person_type if billing else None,
                } if billing else None,
            })

        result.sort(key=lambda x: x['balance'], reverse=True)

        return Response({
            'success': True,
            'payouts': result,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("Error in pending_payouts: %s", e)
        return Response({
            'success': False,
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])
def create_payout(request):
    """
    POST /api/v1/superadmin/payouts/
    Body: { organizer_id, amount, reference? }

    Marks a transfer as done. amount <= balance (partial OK). Rejects when balance <= 0.
    """
    try:
        organizer_id = request.data.get('organizer_id')
        amount = request.data.get('amount')
        reference = request.data.get('reference', '')

        if not organizer_id or amount is None:
            return Response({
                'success': False,
                'message': 'organizer_id and amount are required',
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount))
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'message': 'Invalid amount',
            }, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({
                'success': False,
                'message': 'Amount must be positive',
            }, status=status.HTTP_400_BAD_REQUEST)

        organizer = Organizer.objects.get(id=organizer_id)
        wallet = get_organizer_wallet(organizer)
        balance = wallet['balance']
        if balance <= 0:
            return Response({
                'success': False,
                'message': 'No balance to pay (organizer may owe platform)',
            }, status=status.HTTP_400_BAD_REQUEST)
        if amount > balance:
            return Response({
                'success': False,
                'message': f'Amount exceeds balance ({balance}). Partial payments allowed.',
            }, status=status.HTTP_400_BAD_REQUEST)

        payout = Payout.objects.create(
            organizer=organizer,
            amount=amount,
            paid_at=timezone.now(),
            reference=reference or '',
            created_by=request.user,
        )

        return Response({
            'success': True,
            'payout': {
                'id': str(payout.id),
                'organizer_id': str(organizer.id),
                'amount': float(payout.amount),
                'paid_at': payout.paid_at.isoformat(),
                'reference': payout.reference,
            },
        }, status=status.HTTP_201_CREATED)

    except Organizer.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Organizer not found',
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Error in create_payout: %s", e)
        return Response({
            'success': False,
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def export_payouts(request):
    """
    GET /api/v1/superadmin/pending-payouts/export/?format=xlsx

    Returns XLSX file with bank transfer format.
    Columns: País, Tipo Destinatario, Nombre, Apellido, Tipo Documento, Número Documento,
             Tipo Cuenta, Número Cuenta Bancaria, Banco, Modalidad Origen o Destino, Monto
    """
    try:
        organizers = Organizer.objects.select_related(
            'banking_details', 'billing_details'
        ).prefetch_related('payouts', 'credits').all()

        rows = []
        for org in organizers:
            wallet = get_organizer_wallet(org)
            pending = max(0, wallet['balance'])
            if pending <= 0:
                continue

            try:
                banking = org.banking_details
            except ObjectDoesNotExist:
                banking = None
            try:
                billing = org.billing_details
            except ObjectDoesNotExist:
                billing = None
            if not banking or not billing:
                continue

            # Split account_holder into Nombre, Apellido
            parts = (banking.account_holder or '').strip().split(None, 1)
            nombre = parts[0] if parts else (billing.tax_name or '')
            apellido = parts[1] if len(parts) > 1 else ''

            tipo_destinatario = PERSON_TYPE_TO_RECIPIENT.get(
                billing.person_type, RECIPIENT_TYPES[0][0]
            )

            rows.append({
                'pais': DEFAULT_COUNTRY_CODE,
                'tipo_destinatario': tipo_destinatario,
                'nombre': nombre,
                'apellido': apellido,
                'tipo_documento': 'RUT',
                'numero_documento': billing.tax_id or '',
                'tipo_cuenta': banking.account_type or '',
                'numero_cuenta': banking.account_number or '',
                'banco': banking.bank_name or '',
                'modalidad': 'Destino',
                'monto': int(round(pending)),
            })

        if not rows:
            return Response({
                'success': False,
                'message': 'No pending payouts with complete banking details',
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            import openpyxl
        except ImportError:
            try:
                import xlsxwriter
                return _export_xlsxwriter(rows, request)
            except ImportError:
                return Response({
                    'success': False,
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Transferencias"

        headers = [
            'País', 'Tipo Destinatario', 'Nombre', 'Apellido', 'Tipo de Documento',
            'Número de Documento', 'Tipo de Cuenta', 'Número de Cuenta Bancaria',
            'Banco', 'Modalidad Origen o Destino', 'Monto'
        ]
        ws.append(headers)
        for r in rows:
            ws.append([
                r['pais'], r['tipo_destinatario'], r['nombre'], r['apellido'],
                r['tipo_documento'], r['numero_documento'], r['tipo_cuenta'],
                r['numero_cuenta'], r['banco'], r['modalidad'], r['monto']
            ])

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        from datetime import date
        filename = f"nomina_transferencias_{date.today().isoformat()}.xlsx"
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        logger.exception("Error in export_payouts: %s", e)
        return Response({
            'success': False,
            'message': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _export_xlsxwriter(rows, request):
    """Fallback export using xlsxwriter."""
    import xlsxwriter
    buffer = io.BytesIO()
    wb = xlsxwriter.Workbook(buffer, {'in_memory': True})
    ws = wb.add_worksheet('Transferencias')
    headers = [
        'País', 'Tipo Destinatario', 'Nombre', 'Apellido', 'Tipo de Documento',
        'Número de Documento', 'Tipo de Cuenta', 'Número de Cuenta Bancaria',
        'Banco', 'Modalidad Origen o Destino', 'Monto'
    ]
    for col, h in enumerate(headers):
        ws.write(0, col, h)
    for row_idx, r in enumerate(rows, 1):
        ws.write(row_idx, 0, r['pais'])
        ws.write(row_idx, 1, r['tipo_destinatario'])
        ws.write(row_idx, 2, r['nombre'])
        ws.write(row_idx, 3, r['apellido'])
        ws.write(row_idx, 4, r['tipo_documento'])
        ws.write(row_idx, 5, r['numero_documento'])
        ws.write(row_idx, 6, r['tipo_cuenta'])
        ws.write(row_idx, 7, r['numero_cuenta'])
        ws.write(row_idx, 8, r['banco'])
        ws.write(row_idx, 9, r['modalidad'])
        ws.write(row_idx, 10, r['monto'])
    wb.close()
    buffer.seek(0)
    from datetime import date
    filename = f"nomina_transferencias_{date.today().isoformat()}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsSuperUser])
def bank_options(request):
    """
    GET /api/v1/superadmin/bank-options/
    Returns banks, account types, document types, recipient types for Chile.
    """
    return Response({
        'success': True,
        'banks': [{'value': v, 'label': l} for v, l in CHILE_BANK_CHOICES],
        'account_types': [{'value': v, 'label': l} for v, l in CHILE_ACCOUNT_TYPES],
        'document_types': [{'value': v, 'label': v} for v, _ in CHILE_DOCUMENT_TYPES],
        'recipient_types': [{'value': v, 'label': l} for v, l in RECIPIENT_TYPES],
    }, status=status.HTTP_200_OK)
