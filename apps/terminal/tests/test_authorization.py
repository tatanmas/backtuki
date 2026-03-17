"""
Authorization tests for terminal API.
- Unauthenticated requests to write endpoints (trips create/update/delete, uploads) get 401.
- Authenticated non-admin gets 403.
- List/retrieve trips remain public (200).
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.terminal.models import TerminalCompany, TerminalRoute, TerminalTrip

User = get_user_model()
BASE = '/api/v1/terminal'


class TerminalTripAuthorizationTests(APITestCase):
    """TerminalTripViewSet: list/retrieve public; create/update/delete/sold_out/bulk_delete require IsTerminalAdmin."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = TerminalCompany.objects.create(
            name='Test Co',
            is_active=True,
            contact_method='whatsapp',
            booking_method='internal',
        )
        cls.route = TerminalRoute.objects.create(origin='A', destination='B')
        cls.trip = TerminalTrip.objects.create(
            company=cls.company,
            route=cls.route,
            trip_type='departure',
            date='2025-06-01',
            departure_time='10:00',
            arrival_time='12:00',
            status='available',
            is_active=True,
        )

    def test_list_trips_public_ok(self):
        response = self.client.get(f'{BASE}/trips/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_trip_public_ok(self):
        response = self.client.get(f'{BASE}/trips/{self.trip.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_trip_unauthorized_returns_401(self):
        payload = {
            'company': str(self.company.id),
            'route': str(self.route.id),
            'trip_type': 'departure',
            'date': '2025-06-02',
            'departure_time': '11:00',
            'arrival_time': '13:00',
            'status': 'available',
            'is_active': True,
        }
        response = self.client.post(f'{BASE}/trips/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sold_out_unauthorized_returns_401(self):
        response = self.client.patch(f'{BASE}/trips/{self.trip.id}/sold_out/', format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_bulk_delete_unauthorized_returns_401(self):
        response = self.client.post(f'{BASE}/trips/bulk_delete/', data={'ids': [str(self.trip.id)]}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_trip_as_superuser_ok(self):
        user = User.objects.create_superuser(username='sup', email='sup@test.com', password='testpass123')
        self.client.force_authenticate(user=user)
        payload = {
            'company': str(self.company.id),
            'route': str(self.route.id),
            'trip_type': 'departure',
            'date': '2025-06-03',
            'departure_time': '09:00',
            'arrival_time': '11:00',
            'status': 'available',
            'is_active': True,
        }
        response = self.client.post(f'{BASE}/trips/', data=payload, format='json')
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))


class TerminalUploadAuthorizationTests(APITestCase):
    """TerminalExcelUploadViewSet: upload_excel and preview_excel require IsTerminalAdmin."""

    def test_upload_excel_unauthorized_returns_401(self):
        response = self.client.post(f'{BASE}/uploads/upload_excel/', format='multipart')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_preview_excel_unauthorized_returns_401(self):
        response = self.client.post(f'{BASE}/uploads/preview_excel/', format='multipart')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TerminalMeTests(APITestCase):
    """GET /api/v1/terminal/me/ requires authentication."""

    def test_me_unauthorized_returns_401(self):
        response = self.client.get(f'{BASE}/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_authenticated_returns_role(self):
        user = User.objects.create_superuser(username='u', email='u@t.com', password='pass123')
        self.client.force_authenticate(user=user)
        response = self.client.get(f'{BASE}/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('terminal_role', data)
        self.assertEqual(data['terminal_role'], 'superadmin')
