"""Robust finance center endpoints for superadmin."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from apps.finance.bank_exports import create_bank_export_file, get_exportable_payouts_for_batch
from apps.finance.models import BankExportFile, PayableLine, PayeeAccount, Payout, PayoutAttachment, PayoutBatch, PayoutLineAllocation
from apps.finance.services import create_payout_from_lines, get_finance_platform_settings, payout_totals_for_payee, set_next_payment_dates, sync_all_payables
from apps.organizers.models import Organizer
from apps.organizers.wallet_service import get_organizer_wallet

from ..permissions import IsSuperUser


def _serialize_line(line: PayableLine):
    order = getattr(line, 'order', None)
    metadata = line.metadata or {}
    return {
        'id': str(line.id),
        'source_type': line.source_type,
        'source_reference': line.source_reference,
        'source_label': line.source_label,
        'status': line.status,
        'maturity_status': line.maturity_status,
        'gross_amount': float(line.gross_amount),
        'platform_fee_amount': float(line.platform_fee_amount),
        'payable_amount': float(line.payable_amount),
        'currency': line.currency,
        'effective_at': line.effective_at.isoformat() if line.effective_at else None,
        'due_date': line.due_date.isoformat() if line.due_date else None,
        'paid_at': line.paid_at.isoformat() if line.paid_at else None,
        'metadata': metadata,
        'order_id': str(line.order_id) if line.order_id else None,
        'experience_reservation_id': str(line.experience_reservation_id) if line.experience_reservation_id else None,
        'order_number': order.order_number if order else metadata.get('order_number'),
        'buyer_name': order.buyer_name if order else metadata.get('buyer_name'),
        'product_label': line.source_label,
        'is_sandbox': bool(order.is_sandbox) if order else bool(metadata.get('is_sandbox')),
        'exclude_from_revenue': bool(order.exclude_from_revenue) if order else bool(metadata.get('exclude_from_revenue')),
        'counts_for_revenue': bool(order.counts_for_revenue) if order else bool(metadata.get('counts_for_revenue')),
        'group_type': metadata.get('group_type') or line.source_type,
        'group_id': metadata.get('group_id'),
        'group_label': metadata.get('group_label') or line.source_label,
        'ticket_quantity': metadata.get('ticket_quantity') or 0,
    }


def _serialize_attachment(attachment: PayoutAttachment):
    return {
        'id': str(attachment.id),
        'label': attachment.label,
        'original_name': attachment.original_name,
        'file_url': attachment.file.url if attachment.file else None,
        'created_at': attachment.created_at.isoformat() if attachment.created_at else None,
    }


def _serialize_payout(payout: Payout):
    return {
        'id': str(payout.id),
        'payee_id': str(payout.payee_id),
        'payee_name': payout.payee.display_name,
        'actor_type': payout.payee.actor_type,
        'status': payout.status,
        'amount': float(payout.amount),
        'currency': payout.currency,
        'reference': payout.reference,
        'partner_message': payout.partner_message,
        'bank_reference': payout.bank_reference,
        'batch_id': str(payout.batch_id) if payout.batch_id else None,
        'paid_at': payout.paid_at.isoformat() if payout.paid_at else None,
        'submitted_at': payout.submitted_at.isoformat() if payout.submitted_at else None,
        'created_at': payout.created_at.isoformat() if payout.created_at else None,
        'attachments': [_serialize_attachment(a) for a in payout.attachments.all()],
        'line_ids': [str(allocation.payable_line_id) for allocation in payout.allocations.all()],
    }


def _serialize_line_groups(lines: list[PayableLine]):
    grouped = {}
    for line in lines:
        data = _serialize_line(line)
        group_type = data['group_type'] or data['source_type']
        group_id = data['group_id'] or data['group_label'] or data['source_reference']
        group_key = f'{group_type}:{group_id}'
        if group_key not in grouped:
            grouped[group_key] = {
                'group_key': group_key,
                'group_type': group_type,
                'group_id': group_id,
                'group_label': data['group_label'] or data['source_label'],
                'lines_count': 0,
                'ticket_quantity': 0,
                'gross_amount': 0.0,
                'platform_fee_amount': 0.0,
                'payable_amount': 0.0,
                'open_line_ids': [],
                'order_ids': [],
                'due_date': data['due_date'],
            }
        item = grouped[group_key]
        item['lines_count'] += 1
        item['ticket_quantity'] += data['ticket_quantity'] or 0
        item['gross_amount'] += data['gross_amount']
        item['platform_fee_amount'] += data['platform_fee_amount']
        item['payable_amount'] += data['payable_amount']
        if data['status'] == 'open' and data['maturity_status'] == 'available' and data['payable_amount'] > 0:
            item['open_line_ids'].append(data['id'])
        if data['order_id'] and data['order_id'] not in item['order_ids']:
            item['order_ids'].append(data['order_id'])
        due_date = data['due_date']
        if due_date and (not item['due_date'] or due_date < item['due_date']):
            item['due_date'] = due_date
    return sorted(grouped.values(), key=lambda item: item['payable_amount'], reverse=True)


def _serialize_payee(payee: PayeeAccount, include_lines=False):
    totals = payout_totals_for_payee(payee)
    data = {
        'id': str(payee.id),
        'account_key': payee.account_key,
        'actor_type': payee.actor_type,
        'display_name': payee.display_name,
        'legal_name': payee.legal_name,
        'email': payee.email,
        'phone': payee.phone,
        'currency': payee.currency,
        'status': payee.status,
        'country_code': payee.country_code,
        'tax_name': payee.tax_name,
        'tax_id': payee.tax_id,
        'billing_address': payee.billing_address,
        'bank_name': payee.bank_name,
        'account_type': payee.account_type,
        'account_number': payee.account_number,
        'account_holder': payee.account_holder,
        'has_bank_details': payee.has_bank_details,
        'has_billing_details': payee.has_billing_details,
        'can_export': payee.can_export,
        'next_payment_date': payee.schedule.next_payment_date.isoformat() if hasattr(payee, 'schedule') and payee.schedule.next_payment_date else None,
        **totals,
    }
    if include_lines:
        # Include voided lines (excluded from revenue) so UI can show them and allow re-including
        lines = list(
            payee.payable_lines.select_related('order')
            .order_by('-effective_at', '-created_at')[:300]
        )
        payouts = payee.payouts.select_related('batch').prefetch_related('attachments', 'allocations').order_by('-created_at')[:50]
        data['lines'] = [_serialize_line(line) for line in lines]
        data['line_groups'] = _serialize_line_groups(lines)
        data['payouts'] = [_serialize_payout(payout) for payout in payouts]
    return data


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_sync(request):
    from apps.finance.services_external_revenue import sync_external_revenue_payables
    result = sync_all_payables()
    ext_count = sync_external_revenue_payables()
    set_next_payment_dates()
    return Response({
        'success': True,
        **result,
        'external_revenue_lines_synced': ext_count,
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_overview(request):
    platform_settings = get_finance_platform_settings()
    payees = PayeeAccount.objects.prefetch_related('payable_lines', 'payouts', 'schedule').all()
    overview = {
        'payees_count': payees.count(),
        'organizers_count': payees.filter(actor_type='organizer').count(),
        'creators_count': payees.filter(actor_type='creator').count(),
        'pending_amount': 0,
        'pending_future_amount': 0,
        'paid_amount': 0,
        'partners_missing_bank_data': 0,
        'recent_payouts_count': Payout.objects.count(),
    }
    by_actor = defaultdict(lambda: {'pending_amount': 0, 'paid_amount': 0, 'count': 0})
    for payee in payees:
        totals = payout_totals_for_payee(payee)
        overview['pending_amount'] += totals['pending_amount']
        overview['pending_future_amount'] += totals['pending_future_amount']
        overview['paid_amount'] += totals['paid_amount']
        if not payee.can_export:
            overview['partners_missing_bank_data'] += 1
        by_actor[payee.actor_type]['pending_amount'] += totals['pending_amount']
        by_actor[payee.actor_type]['paid_amount'] += totals['paid_amount']
        by_actor[payee.actor_type]['count'] += 1

    recent_batches = PayoutBatch.objects.order_by('-created_at')[:10]
    return Response({
        'success': True,
        'overview': overview,
        'by_actor': by_actor,
        'platform_settings': {
            'default_next_payment_date': platform_settings.default_next_payment_date.isoformat() if platform_settings.default_next_payment_date else None,
            'default_schedule_frequency': platform_settings.default_schedule_frequency,
            'payout_notes': platform_settings.payout_notes,
        },
        'recent_batches': [
            {
                'id': str(batch.id),
                'name': batch.name,
                'status': batch.status,
                'currency': batch.currency,
                'created_at': batch.created_at.isoformat() if batch.created_at else None,
            }
            for batch in recent_batches
        ],
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_payees(request):
    search = (request.query_params.get('search') or '').strip().lower()
    actor_type = request.query_params.get('actor_type') or ''
    only_with_pending = request.query_params.get('only_with_pending') == '1'
    payees = PayeeAccount.objects.prefetch_related('payable_lines', 'payouts', 'schedule').all()
    if actor_type:
        payees = payees.filter(actor_type=actor_type)
    serialized = []
    for payee in payees:
        if search and search not in f"{payee.display_name} {payee.email} {payee.tax_id}".lower():
            continue
        item = _serialize_payee(payee, include_lines=False)
        if only_with_pending and item['pending_amount'] <= 0:
            continue
        serialized.append(item)
    serialized.sort(key=lambda item: item['pending_amount'], reverse=True)
    return Response({'success': True, 'results': serialized, 'count': len(serialized)})


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def finance_payee_detail(request, payee_id):
    payee = get_object_or_404(PayeeAccount.objects.prefetch_related('payable_lines', 'payouts__attachments', 'payouts__allocations', 'schedule'), id=payee_id)
    if request.method == 'PATCH':
        schedule = getattr(payee, 'schedule', None)
        if schedule is None:
            from apps.finance.models import PayeeSchedule
            schedule = PayeeSchedule.objects.create(payee=payee)
        next_payment_date = request.data.get('next_payment_date')
        if next_payment_date:
            schedule.next_payment_date = next_payment_date
        notes = request.data.get('notes')
        if notes is not None:
            schedule.notes = notes
        frequency = request.data.get('frequency')
        if frequency:
            schedule.frequency = frequency
        schedule.save()
        payee.refresh_from_db()
    return Response({'success': True, 'payee': _serialize_payee(payee, include_lines=True)})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_payouts(request):
    payouts = (
        Payout.objects.select_related('payee', 'batch')
        .prefetch_related('attachments', 'allocations')
        .order_by('-created_at')
    )
    payee_id = request.query_params.get('payee_id')
    status_filter = request.query_params.get('status')
    if payee_id:
        payouts = payouts.filter(payee_id=payee_id)
    if status_filter:
        payouts = payouts.filter(status=status_filter)
    results = [_serialize_payout(payout) for payout in payouts[:200]]
    return Response({'success': True, 'results': results, 'count': payouts.count()})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_create_paid_payout(request):
    payee_id = request.data.get('payee_id')
    line_ids = request.data.get('line_ids') or []
    reference = request.data.get('reference') or ''
    partner_message = request.data.get('partner_message') or ''
    if not payee_id or not line_ids:
        return Response({'success': False, 'message': 'payee_id and line_ids are required'}, status=status.HTTP_400_BAD_REQUEST)
    payee = get_object_or_404(PayeeAccount, id=payee_id)
    try:
        payout = create_payout_from_lines(
            payee=payee,
            line_ids=line_ids,
            reference=reference,
            partner_message=partner_message,
            user=request.user,
        )
    except ValueError as exc:
        return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'success': True, 'payout': _serialize_payout(Payout.objects.prefetch_related('attachments', 'allocations').select_related('payee').get(id=payout.id))})


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def finance_update_payout(request, payout_id):
    payout = get_object_or_404(Payout.objects.select_related('payee').prefetch_related('attachments', 'allocations'), id=payout_id)
    reference = request.data.get('reference')
    partner_message = request.data.get('partner_message')
    update_fields = ['updated_at']
    if reference is not None:
        payout.reference = reference
        update_fields.append('reference')
    if partner_message is not None:
        payout.partner_message = partner_message
        update_fields.append('partner_message')
    payout.save(update_fields=update_fields)
    return Response({'success': True, 'payout': _serialize_payout(payout)})


@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def finance_batches(request):
    if request.method == 'POST':
        name = request.data.get('name') or f"Nómina {timezone.localdate().isoformat()}"
        line_ids = request.data.get('line_ids') or []
        if not line_ids:
            return Response({'success': False, 'message': 'line_ids are required'}, status=status.HTTP_400_BAD_REQUEST)
        lines = list(
            PayableLine.objects.select_related('payee')
            .filter(id__in=line_ids, status='open', maturity_status='available')
            .order_by('payee__display_name', 'effective_at', 'created_at')
        )
        if not lines:
            return Response({'success': False, 'message': 'No payable lines available for batching'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            batch = PayoutBatch.objects.create(name=name, status='approved')
            by_payee = defaultdict(list)
            for line in lines:
                by_payee[line.payee_id].append(line)
            for payee_lines in by_payee.values():
                first_line = payee_lines[0]
                total = sum((line.payable_amount for line in payee_lines), Decimal('0'))
                payout = Payout.objects.create(
                    payee=first_line.payee,
                    batch=batch,
                    status='approved',
                    amount=total,
                    currency=first_line.currency or 'CLP',
                    approved_by=request.user,
                )
                for line in payee_lines:
                    PayoutLineAllocation.objects.create(
                        payout=payout,
                        payable_line=line,
                        amount=line.payable_amount,
                    )
                    line.status = 'batched'
                    line.save(update_fields=['status', 'updated_at'])
        batch = PayoutBatch.objects.prefetch_related('payouts').get(id=batch.id)
        return Response({
            'success': True,
            'batch': {
                'id': str(batch.id),
                'name': batch.name,
                'status': batch.status,
                'payouts_count': batch.payouts.count(),
            },
        })

    batches = PayoutBatch.objects.order_by('-created_at')[:100]
    return Response({
        'success': True,
        'results': [
            {
                'id': str(batch.id),
                'name': batch.name,
                'status': batch.status,
                'currency': batch.currency,
                'payouts_count': batch.payouts.count(),
                'created_at': batch.created_at.isoformat() if batch.created_at else None,
                'paid_at': batch.paid_at.isoformat() if batch.paid_at else None,
            }
            for batch in batches
        ],
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_batch_export(request, batch_id):
    batch = get_object_or_404(PayoutBatch, id=batch_id)
    payouts = get_exportable_payouts_for_batch(batch)
    export_file = create_bank_export_file(payouts=payouts, user=request.user, batch=batch)
    batch.status = 'exported'
    batch.save(update_fields=['status', 'updated_at'])
    payouts.update(status='exported')
    return Response({
        'success': True,
        'export_file': {
            'id': str(export_file.id),
            'filename': export_file.filename,
            'adapter_code': export_file.adapter_code,
            'row_count': export_file.row_count,
            'content': export_file.content,
        },
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_batch_mark_paid(request, batch_id):
    batch = get_object_or_404(PayoutBatch, id=batch_id)
    paid_at = timezone.now()
    payouts = list(Payout.objects.filter(batch=batch).select_related('payee').prefetch_related('allocations'))
    with transaction.atomic():
        for payout in payouts:
            payout.status = 'paid'
            payout.paid_at = paid_at
            payout.save(update_fields=['status', 'paid_at', 'updated_at'])
            allocations = payout.allocations.select_related('payable_line')
            for allocation in allocations:
                line = allocation.payable_line
                line.status = 'paid'
                line.paid_at = paid_at
                line.save(update_fields=['status', 'paid_at', 'updated_at'])
        batch.status = 'paid'
        batch.paid_at = paid_at
        batch.save(update_fields=['status', 'paid_at', 'updated_at'])
    return Response({'success': True})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_export_files(request):
    files = BankExportFile.objects.order_by('-created_at')[:100]
    return Response({
        'success': True,
        'results': [
            {
                'id': str(item.id),
                'filename': item.filename,
                'adapter_code': item.adapter_code,
                'row_count': item.row_count,
                'checksum': item.checksum,
                'created_at': item.created_at.isoformat() if item.created_at else None,
                'content': item.content,
                'batch_id': str(item.batch_id) if item.batch_id else None,
            }
            for item in files
        ],
    })


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def finance_platform_settings(request):
    settings = get_finance_platform_settings()
    if request.method == 'PATCH':
        default_next_payment_date = request.data.get('default_next_payment_date')
        default_schedule_frequency = request.data.get('default_schedule_frequency')
        payout_notes = request.data.get('payout_notes')
        if default_next_payment_date is not None:
            settings.default_next_payment_date = default_next_payment_date or None
        if default_schedule_frequency:
            settings.default_schedule_frequency = default_schedule_frequency
        if payout_notes is not None:
            settings.payout_notes = payout_notes
        settings.save()
    return Response({
        'success': True,
        'settings': {
            'id': str(settings.id),
            'default_next_payment_date': settings.default_next_payment_date.isoformat() if settings.default_next_payment_date else None,
            'default_schedule_frequency': settings.default_schedule_frequency,
            'payout_notes': settings.payout_notes,
        },
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
@parser_classes([MultiPartParser, FormParser])
def finance_payout_attachment_upload(request, payout_id):
    payout = get_object_or_404(Payout, id=payout_id)
    uploads = request.FILES.getlist('files') or ([request.FILES.get('file')] if request.FILES.get('file') else [])
    if not uploads:
        return Response({'success': False, 'message': 'file or files is required'}, status=status.HTTP_400_BAD_REQUEST)
    attachments = []
    for upload in uploads:
        attachment = PayoutAttachment.objects.create(
            payout=payout,
            file=upload,
            original_name=upload.name,
            label=request.data.get('label', ''),
            uploaded_by=request.user,
        )
        attachments.append(_serialize_attachment(attachment))
    return Response({'success': True, 'attachments': attachments, 'attachment': attachments[0]})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_audit(request):
    comparisons = []
    for organizer in Organizer.objects.all():
        wallet = get_organizer_wallet(organizer)
        payee = PayeeAccount.objects.filter(organizer=organizer, actor_type='organizer').first()
        ledger_totals = payout_totals_for_payee(payee) if payee else {
            'pending_amount': 0,
            'paid_amount': 0,
            'gross_sales': 0,
            'platform_fees': 0,
        }
        comparisons.append({
            'organizer_id': str(organizer.id),
            'organizer_name': organizer.name,
            'legacy_balance': wallet['balance'],
            'legacy_total_revenue': wallet['total_revenue'],
            'legacy_payouts_sum': wallet['payouts_sum'],
            'ledger_pending_amount': ledger_totals['pending_amount'],
            'ledger_paid_amount': ledger_totals['paid_amount'],
            'ledger_gross_sales': ledger_totals['gross_sales'],
            'difference_vs_legacy_balance': round(float(wallet['balance']) - float(ledger_totals['pending_amount']), 2),
        })
    comparisons.sort(key=lambda item: abs(item['difference_vs_legacy_balance']), reverse=True)
    return Response({'success': True, 'results': comparisons})
