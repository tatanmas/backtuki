"""
Authorization tests for superadmin API.
- Without token: 401 Unauthorized.
- With normal user token: 403 Forbidden.
- With superuser token: 200 where applicable.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()
BASE = '/api/v1/superadmin'


class SuperAdminAuthorizationTests(APITestCase):
    def setUp(self):
        self.normal_user = User.objects.create_user(
            username='normal',
            email='normal@test.com',
            password='testpass123',
            is_superuser=False,
            is_staff=False,
        )
        self.superuser = User.objects.create_superuser(
            username='super',
            email='super@test.com',
            password='superpass123',
        )

    def test_stats_without_token_returns_401(self):
        response = self.client.get(f'{BASE}/stats/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_stats_with_normal_user_returns_403(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(f'{BASE}/stats/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_stats_with_superuser_returns_200(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(f'{BASE}/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
