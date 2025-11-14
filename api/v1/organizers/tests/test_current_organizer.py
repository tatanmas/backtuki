from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

from apps.organizers.models import Organizer, OrganizerUser
from apps.forms.models import Form


class OrganizerAccessTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.organizer = Organizer.objects.create(
            name="Test Organizer",
            slug="test-organizer",
            contact_email="owner@test.com",
            representative_name="Owner",
            representative_email="owner@test.com",
        )

        self.organizer_user = User.objects.create_user(
            email="member@test.com",
            username="member",
            password="password123",
            is_organizer=True,
        )

        OrganizerUser.objects.create(
            organizer=self.organizer,
            user=self.organizer_user,
            is_admin=True,
            can_manage_events=True,
            can_manage_accommodations=True,
            can_manage_experiences=True,
            can_manage_settings=True,
            can_view_reports=True,
        )

        self.unlinked_user = User.objects.create_user(
            email="guest@test.com",
            username="guest",
            password="password123",
        )

    def test_current_organizer_endpoint_returns_membership(self):
        url = reverse("current_organizer")
        self.client.force_authenticate(user=self.organizer_user)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.organizer.id))
        self.assertEqual(response.data["slug"], self.organizer.slug)

    def test_form_creation_requires_membership(self):
        url = reverse("form-list")
        payload = {"name": "Survey", "status": "active"}

        # Unlinked user should receive 403
        self.client.force_authenticate(user=self.unlinked_user)
        response_no_membership = self.client.post(url, payload, format="json")
        self.assertEqual(response_no_membership.status_code, status.HTTP_403_FORBIDDEN)

        # Organizer member can create
        self.client.force_authenticate(user=self.organizer_user)
        response_membership = self.client.post(url, payload, format="json")
        self.assertEqual(response_membership.status_code, status.HTTP_201_CREATED)

        created_form = Form.objects.get()
        self.assertEqual(created_form.organizer, self.organizer)
        self.assertEqual(created_form.created_by, self.organizer_user)

