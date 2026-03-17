"""Vendor bill posting, aging, and payment allocation services."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, F, Q
from django.utils import timezone

from .models import VendorBill, VendorPayment, VendorPaymentAllocation

logger = logging.getLogger('finance.vendors')
ZERO = Decimal('0')


@transaction.atomic
def post_vendor_bill(bill: VendorBill) -> VendorBill:
    """Transition a vendor bill from draft to posted."""
    if bill.status != 'draft':
        raise ValueError(f'Cannot post bill in status {bill.status}')
    bill.status = 'posted'
    bill.posting_date = bill.posting_date or timezone.localdate()
    bill.save(update_fields=['status', 'posting_date', 'updated_at'])
    logger.info('Vendor bill %s posted (vendor=%s total=%s)', bill.id, bill.vendor_id, bill.total_amount)
    return bill


@transaction.atomic
def void_vendor_bill(bill: VendorBill) -> VendorBill:
    """Void a vendor bill (only if unpaid)."""
    if bill.status in ('paid', 'voided'):
        raise ValueError(f'Cannot void bill in status {bill.status}')
    bill.status = 'voided'
    bill.save(update_fields=['status', 'updated_at'])
    logger.info('Vendor bill %s voided', bill.id)
    return bill


@transaction.atomic
def allocate_vendor_payment(
    *,
    payment: VendorPayment,
    allocations: list[dict],
) -> VendorPayment:
    """Allocate a vendor payment to one or more bills.

    allocations: list of {'bill_id': uuid, 'amount': Decimal}
    """
    total_allocated = ZERO

    for alloc_data in allocations:
        bill = VendorBill.objects.select_for_update().get(id=alloc_data['bill_id'])
        amount = Decimal(str(alloc_data['amount']))

        if amount <= ZERO:
            raise ValueError(f'Allocation amount must be positive for bill {bill.bill_number}')

        remaining = bill.amount_due
        if amount > remaining:
            raise ValueError(
                f'Allocation {amount} exceeds remaining {remaining} on bill {bill.bill_number}'
            )

        VendorPaymentAllocation.objects.create(
            vendor_payment=payment,
            vendor_bill=bill,
            amount=amount,
        )

        total_allocated += amount

        new_paid = bill.amount_paid
        if new_paid >= bill.total_amount:
            bill.status = 'paid'
        elif new_paid > ZERO:
            bill.status = 'partially_paid'
        bill.save(update_fields=['status', 'updated_at'])

    if total_allocated != payment.amount:
        raise ValueError(
            f'Total allocated {total_allocated} does not match payment amount {payment.amount}'
        )

    payment.status = 'completed'
    payment.save(update_fields=['status', 'updated_at'])
    logger.info('Vendor payment %s allocated to %d bills, total=%s', payment.id, len(allocations), total_allocated)
    return payment


def vendor_aging_report(*, as_of=None) -> list[dict]:
    """Generate vendor aging report showing outstanding balances by age bucket."""
    as_of = as_of or timezone.localdate()

    bills = VendorBill.objects.filter(
        status__in=('posted', 'partially_paid'),
    ).select_related('vendor').annotate(
        paid_so_far=Sum('payment_allocations__amount'),
    )

    results = []
    for bill in bills:
        paid = bill.paid_so_far or ZERO
        outstanding = bill.total_amount - paid
        if outstanding <= ZERO:
            continue

        days_overdue = (as_of - bill.due_date).days if bill.due_date <= as_of else 0

        if days_overdue <= 0:
            bucket = 'current'
        elif days_overdue <= 30:
            bucket = '1_30'
        elif days_overdue <= 60:
            bucket = '31_60'
        elif days_overdue <= 90:
            bucket = '61_90'
        else:
            bucket = '90_plus'

        results.append({
            'vendor_id': str(bill.vendor_id),
            'vendor_name': bill.vendor.name,
            'bill_id': str(bill.id),
            'bill_number': bill.bill_number,
            'issue_date': bill.issue_date.isoformat(),
            'due_date': bill.due_date.isoformat(),
            'total_amount': float(bill.total_amount),
            'outstanding': float(outstanding),
            'days_overdue': days_overdue,
            'bucket': bucket,
        })

    return sorted(results, key=lambda r: r['days_overdue'], reverse=True)
