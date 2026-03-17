"""Tests para endpoints legacy de finance center (payees, payouts, batches)."""

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.models import PayableLine, PayeeAccount, PayeeSchedule, Payout, PayoutBatch

from .test_fixtures import FinanceFixturesMixin

BASE = '/api/v1/superadmin/finance'


class FinanceCenterTests(FinanceFixturesMixin, APITestCase):
    def setUp(self):
        self.create_superuser()
        self.client.force_authenticate(user=self.superuser)
        self.create_payee(actor_type='creator')
        self.line_one, self.line_two = self.create_payable_lines(count=2)

    def test_finance_payees_lists_pending_amount(self):
        response = self.client.get(f'{BASE}/payees/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['count'], 1)
        results = [r for r in response.data['results'] if r['id'] == str(self.payee.id)]
        self.assertTrue(results, 'Payee should appear in results')
        self.assertEqual(results[0]['pending_amount'], 5500.0)

    def test_create_paid_payout_marks_lines_paid(self):
        response = self.client.post(
            f'{BASE}/payouts/create-paid/',
            {
                'payee_id': str(self.payee.id),
                'line_ids': [str(self.line_one.id), str(self.line_two.id)],
                'reference': 'Transferencia abril',
                'partner_message': 'Adjuntamos factura y liquidacion.',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(Payout.objects.first().partner_message, 'Adjuntamos factura y liquidacion.')
        self.line_one.refresh_from_db()
        self.line_two.refresh_from_db()
        self.assertEqual(self.line_one.status, 'paid')
        self.assertEqual(self.line_two.status, 'paid')

    def test_create_batch_and_export(self):
        batch_response = self.client.post(
            f'{BASE}/batches/',
            {'line_ids': [str(self.line_one.id), str(self.line_two.id)]},
            format='json',
        )
        self.assertEqual(batch_response.status_code, status.HTTP_200_OK)
        batch_id = batch_response.data['batch']['id']
        export_response = self.client.post(f'{BASE}/batches/{batch_id}/export/')
        self.assertEqual(export_response.status_code, status.HTTP_200_OK)
        self.assertEqual(export_response.data['export_file']['row_count'], 1)
        self.assertEqual(PayoutBatch.objects.get(id=batch_id).status, 'exported')

    def test_upload_attachment_to_payout(self):
        payout = Payout.objects.create(
            payee=self.payee,
            amount=2500,
            currency='CLP',
            status='paid',
        )
        response = self.client.post(
            f'{BASE}/payouts/{payout.id}/attachments/',
            {
                'label': 'Comprobante',
                'file': SimpleUploadedFile('comprobante.txt', b'archivo de prueba', content_type='text/plain'),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payout.refresh_from_db()
        self.assertEqual(payout.attachments.count(), 1)

    def test_update_payout_message(self):
        payout = Payout.objects.create(
            payee=self.payee,
            amount=2500,
            currency='CLP',
            status='paid',
            reference='Transferencia inicial',
        )
        response = self.client.patch(
            f'{BASE}/payouts/{payout.id}/',
            {
                'reference': 'Transferencia final',
                'partner_message': 'Te compartimos la liquidacion final.',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payout.refresh_from_db()
        self.assertEqual(payout.reference, 'Transferencia final')
        self.assertEqual(payout.partner_message, 'Te compartimos la liquidacion final.')

    def test_patch_next_payment_date(self):
        response = self.client.patch(
            f'{BASE}/payees/{self.payee.id}/',
            {'next_payment_date': '2026-04-20'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.payee.refresh_from_db()
        self.assertEqual(self.payee.schedule.next_payment_date.isoformat(), '2026-04-20')
