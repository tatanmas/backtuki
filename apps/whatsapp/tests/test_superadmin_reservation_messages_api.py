"""
Tests for Superadmin WhatsApp reservation-messages API.

GET/PATCH /api/v1/superadmin/whatsapp/reservation-messages/
GET/PATCH .../whatsapp/experiences/<id>/reservation-messages/
GET/PATCH .../whatsapp/accommodations/<uuid>/reservation-messages/
GET/PATCH .../whatsapp/hotels/<uuid>/reservation-messages/
GET/PATCH .../whatsapp/rental-hubs/<uuid>/reservation-messages/
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from apps.whatsapp.models import WhatsAppReservationMessageConfig
from apps.experiences.models import Experience
from apps.accommodations.models import Accommodation, Hotel, RentalHub
from apps.organizers.models import Organizer

User = get_user_model()
BASE = "/api/v1/superadmin/whatsapp"


class ReservationMessagesGlobalAPITests(APITestCase):
    """GET/PATCH reservation-messages/ (global config)."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )

    def test_get_requires_auth(self):
        response = self.client.get(BASE + "/reservation-messages/")
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_get_returns_message_types_and_templates(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + "/reservation-messages/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("message_types", data)
        self.assertIn("templates", data)
        self.assertIn("placeholders", data)
        self.assertIsInstance(data["message_types"], list)
        self.assertIsInstance(data["templates"], dict)
        self.assertIn("reservation_request", data["templates"])

    def test_patch_updates_global_templates(self):
        self.client.force_authenticate(user=self.superuser)
        payload = {
            "templates": {
                "customer_waiting": "Custom global waiting {{nombre_cliente}}",
            },
        }
        response = self.client.patch(
            BASE + "/reservation-messages/",
            data=payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(
            data["templates"].get("customer_waiting"),
            "Custom global waiting {{nombre_cliente}}",
        )
        config = WhatsAppReservationMessageConfig.objects.filter(
            config_key=WhatsAppReservationMessageConfig.CONFIG_KEY
        ).first()
        self.assertIsNotNone(config)
        self.assertEqual(
            config.templates.get("customer_waiting"),
            "Custom global waiting {{nombre_cliente}}",
        )

    def test_patch_requires_templates_dict(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + "/reservation-messages/",
            data={},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_rejects_templates_when_not_dict(self):
        self.client.force_authenticate(user=self.superuser)
        for invalid in ([], "string", 123, None):
            response = self.client.patch(
                BASE + "/reservation-messages/",
                data={"templates": invalid},
                format="json",
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"templates={invalid!r} should be rejected",
            )


class ReservationMessagesExperienceAPITests(APITestCase):
    """GET/PATCH experiences/<id>/reservation-messages/."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.organizer = Organizer.objects.create(name="Org", slug="org-exp")
        self.experience = Experience.objects.create(
            title="Tour",
            slug="tour-exp",
            organizer=self.organizer,
            status="published",
        )

    def test_get_returns_experience_overrides(self):
        self.client.force_authenticate(user=self.superuser)
        url = BASE + f"/experiences/{self.experience.id}/reservation-messages/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["experience_id"], str(self.experience.id))
        self.assertIn("templates", data)
        self.assertIn("message_types", data)

    def test_patch_updates_experience_templates(self):
        self.client.force_authenticate(user=self.superuser)
        url = BASE + f"/experiences/{self.experience.id}/reservation-messages/"
        payload = {"templates": {"reservation_request": "Custom for experience"}}
        response = self.client.patch(url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.experience.refresh_from_db()
        self.assertEqual(
            self.experience.whatsapp_message_templates.get("reservation_request"),
            "Custom for experience",
        )

    def test_get_404_for_invalid_experience_id(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + "/experiences/00000000-0000-0000-0000-000000000000/reservation-messages/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ReservationMessagesAccommodationAPITests(APITestCase):
    """GET/PATCH accommodations/<uuid>/reservation-messages/."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.organizer = Organizer.objects.create(name="Org", slug="org-acc")
        self.accommodation = Accommodation.objects.create(
            title="Cabin",
            slug="cabin-acc",
            organizer=self.organizer,
            status="published",
        )

    def test_get_returns_accommodation_overrides(self):
        self.client.force_authenticate(user=self.superuser)
        url = BASE + f"/accommodations/{self.accommodation.id}/reservation-messages/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["accommodation_id"], str(self.accommodation.id))

    def test_patch_updates_accommodation_templates(self):
        self.client.force_authenticate(user=self.superuser)
        url = BASE + f"/accommodations/{self.accommodation.id}/reservation-messages/"
        payload = {"templates": {"customer_waiting": "Room message"}}
        response = self.client.patch(url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.accommodation.refresh_from_db()
        self.assertEqual(
            self.accommodation.whatsapp_message_templates.get("customer_waiting"),
            "Room message",
        )

    def test_get_404_for_invalid_accommodation_uuid(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(
            BASE + "/accommodations/00000000-0000-0000-0000-000000000000/reservation-messages/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ReservationMessagesHotelAPITests(APITestCase):
    """GET/PATCH hotels/<uuid>/reservation-messages/."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.hotel = Hotel.objects.create(name="Hotel Test", slug="hotel-test")

    def test_get_and_patch_hotel_templates(self):
        self.client.force_authenticate(user=self.superuser)
        url = BASE + f"/hotels/{self.hotel.id}/reservation-messages/"
        r1 = self.client.get(url)
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r1.json()["hotel_id"], str(self.hotel.id))

        r2 = self.client.patch(
            url,
            data={"templates": {"customer_confirmation": "Hotel confirm"}},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.hotel.refresh_from_db()
        self.assertEqual(
            self.hotel.whatsapp_message_templates.get("customer_confirmation"),
            "Hotel confirm",
        )


class ReservationMessagesRentalHubAPITests(APITestCase):
    """GET/PATCH rental-hubs/<uuid>/reservation-messages/."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.hub = RentalHub.objects.create(name="Central Test", slug="central-test")

    def test_get_and_patch_rental_hub_templates(self):
        self.client.force_authenticate(user=self.superuser)
        url = BASE + f"/rental-hubs/{self.hub.id}/reservation-messages/"
        r1 = self.client.get(url)
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r1.json()["rental_hub_id"], str(self.hub.id))

        r2 = self.client.patch(
            url,
            data={"templates": {"reminder": "Hub reminder"}},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.hub.refresh_from_db()
        self.assertEqual(
            self.hub.whatsapp_message_templates.get("reminder"),
            "Hub reminder",
        )
