"""Tests para services_vendors."""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import ExpenseCategory, ExpenseLine, TaxTreatment, Vendor, VendorBill, VendorPayment
from apps.finance.services_vendors import (
    allocate_vendor_payment,
    post_vendor_bill,
    vendor_aging_report,
    void_vendor_bill,
)

from .test_fixtures import FinanceFixturesMixin


class VendorsServiceTests(FinanceFixturesMixin, TestCase):
    def setUp(self):
        self.create_vendor_and_bill()
        self.tax = TaxTreatment.objects.get_or_create(
            code='IVA19',
            defaults={'name': 'IVA 19%', 'tax_type': 'vat_credit', 'rate': Decimal('0.19'), 'is_recoverable': True},
        )[0]
        self.cat = ExpenseCategory.objects.get_or_create(
            code='GEN',
            defaults={'name': 'Gastos generales'},
        )[0]

    def test_post_vendor_bill(self):
        post_vendor_bill(self.bill)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, 'posted')

    def test_void_vendor_bill_draft(self):
        void_vendor_bill(self.bill)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, 'voided')

    def test_void_vendor_bill_paid_raises(self):
        self.bill.status = 'paid'
        self.bill.save()
        with self.assertRaises(ValueError):
            void_vendor_bill(self.bill)

    def test_allocate_vendor_payment(self):
        self.bill.status = 'posted'
        self.bill.save()
        payment = VendorPayment.objects.create(
            vendor=self.vendor,
            amount=Decimal('119000'),
            payment_date=self.bill.due_date,
            status='pending',
        )
        allocate_vendor_payment(
            payment=payment,
            allocations=[{'bill_id': str(self.bill.id), 'amount': Decimal('119000')}],
        )
        payment.refresh_from_db()
        self.bill.refresh_from_db()
        self.assertEqual(payment.status, 'completed')
        self.assertEqual(self.bill.status, 'paid')

    def test_vendor_aging_report(self):
        self.bill.status = 'posted'
        self.bill.save()
        report = vendor_aging_report()
        self.assertIsInstance(report, list)
        items = [r for r in report if r['bill_id'] == str(self.bill.id)]
        if items:
            self.assertIn('outstanding', items[0])
            self.assertIn('days_overdue', items[0])
