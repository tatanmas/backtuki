"""Treasury, bank account, and processor settlement endpoints for superadmin."""

from __future__ import annotations

from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.finance.models import (
    BankAccount,
    BankBalanceSnapshot,
    BankReconciliation,
    BankStatementLine,
    ProcessorSettlement,
)
from apps.finance.services_bank_reconciliation import (
    classify_statement_line,
    get_matchable_payouts,
    get_matchable_processor_settlements,
    get_matchable_vendor_payments,
    get_reconciliation_summary,
    ignore_statement_line,
    list_statement_lines,
    unclassify_statement_line,
)
from apps.finance.services_treasury import get_treasury_position

from ..permissions import IsSuperUser


# ---------------------------------------------------------------------------
# Bank Accounts CRUD
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def finance_bank_accounts(request):
    if request.method == 'POST':
        account = BankAccount.objects.create(
            name=request.data.get('name', ''),
            bank_name=request.data.get('bank_name', ''),
            account_number_masked=request.data.get('account_number_masked', ''),
            currency=request.data.get('currency', 'CLP'),
            country_code=request.data.get('country_code', 'CL'),
        )
        return Response({
            'success': True,
            'bank_account': {
                'id': str(account.id),
                'name': account.name,
                'bank_name': account.bank_name,
                'currency': account.currency,
            },
        }, status=status.HTTP_201_CREATED)

    include_inactive = request.query_params.get('include_inactive') == '1'
    qs = BankAccount.objects.order_by('name')
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return Response({
        'success': True,
        'results': [
            {
                'id': str(a.id),
                'name': a.name,
                'bank_name': a.bank_name,
                'account_number_masked': a.account_number_masked,
                'currency': a.currency,
                'country_code': a.country_code,
                'is_active': a.is_active,
            }
            for a in qs
        ],
    })


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def finance_bank_account_detail(request, account_id):
    account = get_object_or_404(BankAccount, id=account_id)
    if request.method == 'PATCH':
        for field in ['name', 'bank_name', 'account_number_masked', 'currency', 'country_code', 'is_active']:
            val = request.data.get(field)
            if val is not None:
                setattr(account, field, val)
        account.save()
    return Response({
        'success': True,
        'bank_account': {
            'id': str(account.id),
            'name': account.name,
            'bank_name': account.bank_name,
            'account_number_masked': account.account_number_masked,
            'currency': account.currency,
            'is_active': account.is_active,
        },
    })


# ---------------------------------------------------------------------------
# Bank Statements Import
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_bank_statements_import(request):
    """Import bank statement lines from a JSON payload.
    Accepts bank_account_id (UUID) or bank_account_name (lookup by name).
    """
    account_id = request.data.get('bank_account_id')
    account_name = request.data.get('bank_account_name', '').strip()
    lines_data = request.data.get('lines', [])
    if not lines_data:
        return Response(
            {'success': False, 'message': 'lines is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if account_id:
        account = get_object_or_404(BankAccount, id=account_id)
    elif account_name:
        account = BankAccount.objects.filter(name__iexact=account_name, is_active=True).first()
        if not account:
            return Response(
                {'success': False, 'message': f'Bank account "{account_name}" not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
    else:
        return Response(
            {'success': False, 'message': 'bank_account_id or bank_account_name is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    created = 0

    for line_data in lines_data:
        BankStatementLine.objects.create(
            bank_account=account,
            statement_date=line_data.get('statement_date'),
            value_date=line_data.get('value_date') or None,
            external_reference=line_data.get('external_reference', ''),
            description=line_data.get('description', ''),
            amount=line_data.get('amount', 0),
            balance_after=line_data.get('balance_after') or None,
        )
        created += 1

    if lines_data:
        last = lines_data[-1]
        if last.get('balance_after') is not None:
            BankBalanceSnapshot.objects.update_or_create(
                bank_account=account,
                snapshot_date=last.get('statement_date'),
                defaults={
                    'balance': last['balance_after'],
                    'source': 'statement_import',
                },
            )

    return Response({'success': True, 'lines_created': created})


# ---------------------------------------------------------------------------
# Processor Settlements
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def finance_processor_settlements(request):
    if request.method == 'POST':
        ps = ProcessorSettlement.objects.create(
            processor_name=request.data.get('processor_name', ''),
            settlement_reference=request.data.get('settlement_reference', ''),
            currency=request.data.get('currency', 'CLP'),
            gross_amount=request.data.get('gross_amount', 0),
            fees_amount=request.data.get('fees_amount', 0),
            net_amount=request.data.get('net_amount', 0),
            payment_date=request.data.get('payment_date'),
            deposit_date=request.data.get('deposit_date') or None,
        )
        return Response({
            'success': True,
            'settlement': {
                'id': str(ps.id),
                'processor_name': ps.processor_name,
                'net_amount': float(ps.net_amount),
                'status': ps.status,
            },
        }, status=status.HTTP_201_CREATED)

    qs = ProcessorSettlement.objects.order_by('-payment_date')[:200]
    return Response({
        'success': True,
        'results': [
            {
                'id': str(ps.id),
                'processor_name': ps.processor_name,
                'settlement_reference': ps.settlement_reference,
                'gross_amount': float(ps.gross_amount),
                'fees_amount': float(ps.fees_amount),
                'net_amount': float(ps.net_amount),
                'payment_date': ps.payment_date.isoformat(),
                'deposit_date': ps.deposit_date.isoformat() if ps.deposit_date else None,
                'status': ps.status,
            }
            for ps in qs
        ],
    })


# ---------------------------------------------------------------------------
# Treasury Position
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_treasury_position(request):
    as_of = request.query_params.get('as_of')
    if as_of:
        try:
            from datetime import date
            as_of = date.fromisoformat(as_of)
        except (ValueError, TypeError):
            as_of = None
    position = get_treasury_position(as_of=as_of)
    return Response({'success': True, **position})


# ---------------------------------------------------------------------------
# Bank Reconciliations
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_bank_reconciliations(request):
    qs = BankReconciliation.objects.select_related('bank_account').order_by('-period_end')[:100]
    return Response({
        'success': True,
        'results': [
            {
                'id': str(r.id),
                'bank_account_name': r.bank_account.name,
                'period_start': r.period_start.isoformat(),
                'period_end': r.period_end.isoformat(),
                'status': r.status,
                'book_balance': float(r.book_balance),
                'bank_balance': float(r.bank_balance),
                'unexplained_difference': float(r.unexplained_difference),
            }
            for r in qs
        ],
    })


# ---------------------------------------------------------------------------
# Bank Statement Lines (reconciliation)
# ---------------------------------------------------------------------------

def _serialize_statement_line(line: BankStatementLine) -> dict:
    return {
        'id': str(line.id),
        'bank_account_id': str(line.bank_account_id),
        'bank_account_name': line.bank_account.name,
        'statement_date': line.statement_date.isoformat(),
        'value_date': line.value_date.isoformat() if line.value_date else None,
        'external_reference': line.external_reference or '',
        'description': line.description or '',
        'amount': float(line.amount),
        'balance_after': float(line.balance_after) if line.balance_after else None,
        'status': line.status,
        'movement_type': line.movement_type or '',
        'classification_note': line.classification_note or '',
        'matched_payout': {
            'id': str(line.matched_payout_id),
            'payee_name': line.matched_payout.payee.display_name,
            'amount': float(line.matched_payout.amount),
        } if line.matched_payout_id else None,
        'matched_vendor_payment': {
            'id': str(line.matched_vendor_payment_id),
            'vendor_name': line.matched_vendor_payment.vendor.name,
            'amount': float(line.matched_vendor_payment.amount),
        } if line.matched_vendor_payment_id else None,
        'matched_processor_settlement': {
            'id': str(line.matched_processor_settlement_id),
            'processor_name': line.matched_processor_settlement.processor_name,
            'net_amount': float(line.matched_processor_settlement.net_amount),
        } if line.matched_processor_settlement_id else None,
    }


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_bank_statement_lines(request):
    """List bank statement lines with filters for reconciliation."""
    bank_account_id = request.query_params.get('bank_account_id')
    status_filter = request.query_params.get('status')
    movement_type = request.query_params.get('movement_type')
    from_date = request.query_params.get('from_date')
    to_date = request.query_params.get('to_date')
    limit = min(int(request.query_params.get('limit', 200)), 500)
    offset = int(request.query_params.get('offset', 0))

    lines, total = list_statement_lines(
        bank_account_id=bank_account_id or None,
        status=status_filter or None,
        movement_type=movement_type or None,
        from_date=from_date or None,
        to_date=to_date or None,
        limit=limit,
        offset=offset,
    )
    return Response({
        'success': True,
        'results': [_serialize_statement_line(l) for l in lines],
        'count': len(lines),
        'total': total,
    })


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def finance_bank_statement_line_classify(request, line_id):
    """Classify a bank statement line."""
    data = request.data
    movement_type = data.get('movement_type', '')
    classification_note = data.get('classification_note', '')
    payout_id = data.get('payout_id')
    vendor_payment_id = data.get('vendor_payment_id')
    processor_settlement_id = data.get('processor_settlement_id')
    create_manual_expense = data.get('create_manual_expense', False)
    expense_ledger_account_code = data.get('expense_ledger_account_code')

    try:
        classify_statement_line(
            line_id=line_id,
            movement_type=movement_type,
            classification_note=classification_note,
            payout_id=payout_id,
            vendor_payment_id=vendor_payment_id,
            processor_settlement_id=processor_settlement_id,
            create_manual_expense=create_manual_expense,
            expense_ledger_account_code=expense_ledger_account_code,
            user=request.user,
        )
        line = BankStatementLine.objects.select_related(
            'bank_account',
            'matched_payout__payee',
            'matched_vendor_payment__vendor',
            'matched_processor_settlement',
            'matched_journal_entry',
        ).get(id=line_id)
    except BankStatementLine.DoesNotExist:
        return Response(
            {'success': False, 'message': 'Line not found'},
            status=status.HTTP_404_NOT_FOUND,
        )
    except ValueError as e:
        return Response(
            {'success': False, 'message': str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({
        'success': True,
        'line': _serialize_statement_line(line),
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_bank_statement_line_unclassify(request, line_id):
    """Clear classification of a bank statement line."""
    try:
        unclassify_statement_line(line_id)
        line = BankStatementLine.objects.select_related(
            'bank_account',
            'matched_payout__payee',
            'matched_vendor_payment__vendor',
            'matched_processor_settlement',
            'matched_journal_entry',
        ).get(id=line_id)
    except BankStatementLine.DoesNotExist:
        return Response(
            {'success': False, 'message': 'Line not found'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response({
        'success': True,
        'line': _serialize_statement_line(line),
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_bank_statement_line_ignore(request, line_id):
    """Mark a bank statement line as ignored."""
    try:
        ignore_statement_line(line_id)
        line = BankStatementLine.objects.select_related(
            'bank_account',
            'matched_payout__payee',
            'matched_vendor_payment__vendor',
            'matched_processor_settlement',
            'matched_journal_entry',
        ).get(id=line_id)
    except BankStatementLine.DoesNotExist:
        return Response(
            {'success': False, 'message': 'Line not found'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response({
        'success': True,
        'line': _serialize_statement_line(line),
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_bank_statement_matchable_payouts(request):
    """List payouts that can be matched to bank lines (paid, not yet reconciled)."""
    amount = request.query_params.get('amount')
    amount_dec = Decimal(amount) if amount else None
    payouts = get_matchable_payouts(amount=amount_dec)
    return Response({
        'success': True,
        'results': [
            {
                'id': str(p.id),
                'payee_name': p.payee.display_name,
                'amount': float(p.amount),
                'paid_at': p.paid_at.isoformat() if p.paid_at else None,
                'reference': p.reference or '',
            }
            for p in payouts
        ],
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_bank_statement_matchable_vendor_payments(request):
    """List vendor payments that can be matched to bank lines."""
    amount = request.query_params.get('amount')
    amount_dec = Decimal(amount) if amount else None
    vps = get_matchable_vendor_payments(amount=amount_dec)
    return Response({
        'success': True,
        'results': [
            {
                'id': str(vp.id),
                'vendor_name': vp.vendor.name,
                'amount': float(vp.amount),
                'payment_date': vp.payment_date.isoformat(),
                'reference': vp.reference or '',
            }
            for vp in vps
        ],
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_bank_statement_matchable_settlements(request):
    """List processor settlements that can be matched to bank lines."""
    amount = request.query_params.get('amount')
    amount_dec = Decimal(amount) if amount else None
    settlements = get_matchable_processor_settlements(amount=amount_dec)
    return Response({
        'success': True,
        'results': [
            {
                'id': str(ps.id),
                'processor_name': ps.processor_name,
                'settlement_reference': ps.settlement_reference,
                'net_amount': float(ps.net_amount),
                'payment_date': ps.payment_date.isoformat(),
            }
            for ps in settlements
        ],
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_bank_statement_summary(request, account_id):
    """Reconciliation summary for a bank account."""
    summary = get_reconciliation_summary(account_id)
    return Response({'success': True, 'summary': summary})
