"""Vendor, expense, and payment endpoints for superadmin."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.finance.models import (
    CostCenter,
    ExpenseCategory,
    ExpenseLine,
    TaxTreatment,
    Vendor,
    VendorBill,
    VendorPayment,
)
from apps.finance.services_vendors import (
    allocate_vendor_payment,
    post_vendor_bill,
    vendor_aging_report,
    void_vendor_bill,
)

from ..permissions import IsSuperUser


def _serialize_vendor(v: Vendor) -> dict:
    return {
        'id': str(v.id),
        'vendor_type': v.vendor_type,
        'name': v.name,
        'legal_name': v.legal_name,
        'tax_id': v.tax_id,
        'country_code': v.country_code,
        'currency': v.currency,
        'email': v.email,
        'status': v.status,
    }


def _parse_date(val):
    """Parse date from string (YYYY-MM-DD) or return date object as-is."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return date.fromisoformat(val)
    return val


def _serialize_bill(b: VendorBill) -> dict:
    issue = b.issue_date
    due = b.due_date
    return {
        'id': str(b.id),
        'vendor_id': str(b.vendor_id),
        'vendor_name': b.vendor.name if b.vendor else None,
        'bill_number': b.bill_number,
        'issue_date': issue.isoformat() if hasattr(issue, 'isoformat') else str(issue),
        'due_date': due.isoformat() if hasattr(due, 'isoformat') else str(due),
        'subtotal_amount': float(b.subtotal_amount),
        'tax_amount': float(b.tax_amount),
        'total_amount': float(b.total_amount),
        'status': b.status,
        'amount_paid': float(b.amount_paid),
        'amount_due': float(b.amount_due),
        'description': b.description,
        'created_at': b.created_at.isoformat() if b.created_at else None,
    }


# ---------------------------------------------------------------------------
# Vendors CRUD
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def finance_vendors(request):
    if request.method == 'POST':
        vendor = Vendor.objects.create(
            vendor_type=request.data.get('vendor_type', 'local'),
            name=request.data.get('name', ''),
            legal_name=request.data.get('legal_name', ''),
            tax_id=request.data.get('tax_id', ''),
            document_type=request.data.get('document_type', ''),
            country_code=request.data.get('country_code', 'CL'),
            currency=request.data.get('currency', 'CLP'),
            email=request.data.get('email', ''),
            phone=request.data.get('phone', ''),
            address=request.data.get('address', ''),
            bank_name=request.data.get('bank_name', ''),
            account_type=request.data.get('account_type', ''),
            account_number=request.data.get('account_number', ''),
            account_holder=request.data.get('account_holder', ''),
        )
        return Response({'success': True, 'vendor': _serialize_vendor(vendor)}, status=status.HTTP_201_CREATED)

    status_filter = request.query_params.get('status')
    include_inactive = request.query_params.get('include_inactive') == '1'
    qs = Vendor.objects.order_by('name')
    if include_inactive or status_filter == 'all':
        pass  # no filter - show all
    elif status_filter and status_filter != 'all':
        qs = qs.filter(status=status_filter)
    else:
        qs = qs.filter(status='active')  # default: active only
    vendors = qs
    return Response({
        'success': True,
        'results': [_serialize_vendor(v) for v in vendors],
        'count': vendors.count(),
    })


@api_view(['GET', 'PATCH'])
@permission_classes([IsSuperUser])
def finance_vendor_detail(request, vendor_id):
    vendor = get_object_or_404(Vendor, id=vendor_id)
    if request.method == 'PATCH':
        for field in ['name', 'legal_name', 'tax_id', 'email', 'phone', 'address',
                       'vendor_type', 'country_code', 'currency', 'status',
                       'bank_name', 'account_type', 'account_number', 'account_holder']:
            val = request.data.get(field)
            if val is not None:
                setattr(vendor, field, val)
        vendor.save()
    return Response({'success': True, 'vendor': _serialize_vendor(vendor)})


# ---------------------------------------------------------------------------
# Vendor Bills CRUD
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_vendor_bills_create_from_json(request):
    """Bulk create vendor bills from JSON. Accepts vendor_id or vendor (object) per bill."""
    bills_data = request.data.get('bills', [])
    if not bills_data:
        return Response(
            {'success': False, 'message': 'bills is required (array)'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    created = []
    errors = []
    with transaction.atomic():
        for i, b in enumerate(bills_data):
            try:
                vendor = None
                if b.get('vendor_id'):
                    vendor = get_object_or_404(Vendor, id=b['vendor_id'])
                elif b.get('vendor') and isinstance(b['vendor'], dict):
                    vd = b['vendor']
                    name = (vd.get('name') or '').strip()
                    tax_id = (vd.get('tax_id') or '').strip()
                    if not name:
                        errors.append({'index': i, 'message': 'vendor.name required when using vendor object'})
                        continue
                    q = Q(name__iexact=name)
                    if tax_id:
                        q |= Q(tax_id=tax_id)
                    vendor = Vendor.objects.filter(q).first()
                    if not vendor:
                        vendor = Vendor.objects.create(
                            name=name,
                            legal_name=vd.get('legal_name', ''),
                            tax_id=tax_id,
                            vendor_type=vd.get('vendor_type', 'local'),
                            country_code=vd.get('country_code', 'CL'),
                            currency=vd.get('currency', 'CLP'),
                            email=vd.get('email', ''),
                            phone=vd.get('phone', ''),
                            address=vd.get('address', ''),
                        )
                if not vendor:
                    errors.append({'index': i, 'message': 'vendor_id or vendor (object with name) required'})
                    continue
                bill = VendorBill.objects.create(
                    vendor=vendor,
                    bill_number=str(b.get('bill_number', '')).strip() or f'BLK-{i + 1}',
                    issue_date=_parse_date(b['issue_date']),
                    due_date=_parse_date(b['due_date']),
                    service_period_start=_parse_date(b.get('service_period_start')),
                    service_period_end=_parse_date(b.get('service_period_end')),
                    currency=b.get('currency', 'CLP'),
                    subtotal_amount=b.get('subtotal_amount', b.get('total_amount', 0)),
                    tax_amount=b.get('tax_amount', 0),
                    total_amount=b.get('total_amount', 0),
                    external_reference=b.get('external_reference', ''),
                    description=b.get('description', ''),
                )
                for line_data in b.get('expense_lines', []):
                    ec_id = line_data.get('expense_category_id')
                    tt_id = line_data.get('tax_treatment_id')
                    if ec_id and tt_id:
                        ExpenseLine.objects.create(
                            vendor_bill=bill,
                            expense_category_id=ec_id,
                            cost_center_id=line_data.get('cost_center_id') or None,
                            tax_treatment_id=tt_id,
                            description=line_data.get('description', ''),
                            net_amount=line_data.get('net_amount', line_data.get('gross_amount', 0)),
                            tax_amount=line_data.get('tax_amount', 0),
                            gross_amount=line_data.get('gross_amount', line_data.get('net_amount', 0) + line_data.get('tax_amount', 0)),
                        )
                created.append(_serialize_bill(bill))
            except Exception as e:
                errors.append({'index': i, 'message': str(e)})
    return Response({
        'success': True,
        'created': len(created),
        'bills': created,
        'errors': errors if errors else None,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def finance_vendor_bills(request):
    if request.method == 'POST':
        vendor = get_object_or_404(Vendor, id=request.data.get('vendor_id'))
        bill = VendorBill.objects.create(
            vendor=vendor,
            bill_number=request.data.get('bill_number', ''),
            issue_date=request.data.get('issue_date'),
            due_date=request.data.get('due_date'),
            service_period_start=request.data.get('service_period_start') or None,
            service_period_end=request.data.get('service_period_end') or None,
            currency=request.data.get('currency', 'CLP'),
            subtotal_amount=request.data.get('subtotal_amount', 0),
            tax_amount=request.data.get('tax_amount', 0),
            total_amount=request.data.get('total_amount', 0),
            external_reference=request.data.get('external_reference', ''),
            description=request.data.get('description', ''),
        )

        for line_data in request.data.get('expense_lines', []):
            ExpenseLine.objects.create(
                vendor_bill=bill,
                expense_category_id=line_data.get('expense_category_id'),
                cost_center_id=line_data.get('cost_center_id') or None,
                tax_treatment_id=line_data.get('tax_treatment_id'),
                description=line_data.get('description', ''),
                product_type=line_data.get('product_type') or None,
                product_id=line_data.get('product_id') or None,
                net_amount=line_data.get('net_amount', 0),
                tax_amount=line_data.get('tax_amount', 0),
                gross_amount=line_data.get('gross_amount', 0),
            )

        return Response({'success': True, 'bill': _serialize_bill(bill)}, status=status.HTTP_201_CREATED)

    bills = VendorBill.objects.select_related('vendor').order_by('-issue_date')
    vendor_id = request.query_params.get('vendor_id')
    if vendor_id:
        bills = bills.filter(vendor_id=vendor_id)
    status_filter = request.query_params.get('status')
    if status_filter:
        bills = bills.filter(status=status_filter)

    return Response({
        'success': True,
        'results': [_serialize_bill(b) for b in bills[:200]],
        'count': bills.count(),
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_vendor_bill_post(request, bill_id):
    bill = get_object_or_404(VendorBill, id=bill_id)
    try:
        post_vendor_bill(bill)
    except ValueError as exc:
        return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'success': True, 'bill': _serialize_bill(bill)})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def finance_vendor_bill_void(request, bill_id):
    bill = get_object_or_404(VendorBill, id=bill_id)
    try:
        void_vendor_bill(bill)
    except ValueError as exc:
        return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'success': True, 'bill': _serialize_bill(bill)})


# ---------------------------------------------------------------------------
# Vendor Payments
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def finance_vendor_payments(request):
    if request.method == 'POST':
        vendor = get_object_or_404(Vendor, id=request.data.get('vendor_id'))
        payment = VendorPayment.objects.create(
            vendor=vendor,
            currency=request.data.get('currency', 'CLP'),
            payment_date=request.data.get('payment_date'),
            amount=request.data.get('amount'),
            reference=request.data.get('reference', ''),
            bank_reference=request.data.get('bank_reference', ''),
        )

        allocations = request.data.get('allocations', [])
        if allocations:
            try:
                allocate_vendor_payment(payment=payment, allocations=allocations)
            except ValueError as exc:
                payment.delete()
                return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'payment': {
                'id': str(payment.id),
                'vendor_name': vendor.name,
                'amount': float(payment.amount),
                'status': payment.status,
            },
        }, status=status.HTTP_201_CREATED)

    payments = VendorPayment.objects.select_related('vendor').order_by('-payment_date')[:200]
    return Response({
        'success': True,
        'results': [
            {
                'id': str(p.id),
                'vendor_id': str(p.vendor_id),
                'vendor_name': p.vendor.name,
                'amount': float(p.amount),
                'currency': p.currency,
                'payment_date': p.payment_date.isoformat(),
                'status': p.status,
                'reference': p.reference,
            }
            for p in payments
        ],
    })


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_vendor_aging(request):
    report = vendor_aging_report()
    return Response({'success': True, 'results': report, 'count': len(report)})


# ---------------------------------------------------------------------------
# Reference data CRUD (categories, cost centers, tax treatments)
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def finance_expense_categories(request):
    if request.method == 'POST':
        cat = ExpenseCategory.objects.create(
            code=request.data.get('code', ''),
            name=request.data.get('name', ''),
            cost_center_required=request.data.get('cost_center_required', False),
        )
        return Response({'success': True, 'category': {'id': str(cat.id), 'code': cat.code, 'name': cat.name}}, status=status.HTTP_201_CREATED)

    cats = ExpenseCategory.objects.filter(is_active=True).order_by('code')
    return Response({
        'success': True,
        'results': [{'id': str(c.id), 'code': c.code, 'name': c.name} for c in cats],
    })


@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def finance_cost_centers(request):
    if request.method == 'POST':
        cc = CostCenter.objects.create(
            code=request.data.get('code', ''),
            name=request.data.get('name', ''),
        )
        return Response({'success': True, 'cost_center': {'id': str(cc.id), 'code': cc.code, 'name': cc.name}}, status=status.HTTP_201_CREATED)

    ccs = CostCenter.objects.filter(is_active=True).order_by('code')
    return Response({
        'success': True,
        'results': [{'id': str(c.id), 'code': c.code, 'name': c.name} for c in ccs],
    })


@api_view(['GET', 'POST'])
@permission_classes([IsSuperUser])
def finance_tax_treatments(request):
    if request.method == 'POST':
        tt = TaxTreatment.objects.create(
            code=request.data.get('code', ''),
            name=request.data.get('name', ''),
            tax_type=request.data.get('tax_type', 'no_vat'),
            rate=request.data.get('rate', 0),
            is_recoverable=request.data.get('is_recoverable', False),
        )
        return Response({
            'success': True,
            'tax_treatment': {'id': str(tt.id), 'code': tt.code, 'name': tt.name, 'tax_type': tt.tax_type},
        }, status=status.HTTP_201_CREATED)

    tts = TaxTreatment.objects.filter(is_active=True).order_by('code')
    return Response({
        'success': True,
        'results': [
            {'id': str(t.id), 'code': t.code, 'name': t.name, 'tax_type': t.tax_type, 'rate': float(t.rate), 'is_recoverable': t.is_recoverable}
            for t in tts
        ],
    })
