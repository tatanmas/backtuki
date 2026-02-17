"""
API tests for WhatsApp accommodation: generate-reservation-code, reservation-by-code.
"""
from django.test import TestCase
from rest_framework.test import APIClient
from django.utils import timezone
from datetime import timedelta

from apps.whatsapp.models import WhatsAppReservationCode
from core.testing import (
    create_accommodation,
    create_whatsapp_message,
    create_reservation_code_for_accommodation,
    create_reservation_code_raw,
    create_whatsapp_reservation_request,
    create_accommodation_reservation,
)
from core.testing.fixtures import CHECKOUT_DATA_ACCOMMODATION_FULL


class GenerateReservationCodeAccommodationAPITests(TestCase):
    """POST /api/v1/whatsapp/generate-reservation-code/ with accommodation_id."""

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/whatsapp/generate-reservation-code/"
        self.accommodation = create_accommodation()

    def test_post_accommodation_success(self):
        """accommodation_id + checkout_data → 201, code RES-*, product_type accommodation, expires_at."""
        payload = {
            "accommodation_id": str(self.accommodation.id),
            "checkout_data": CHECKOUT_DATA_ACCOMMODATION_FULL.copy(),
        }
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("code", data)
        self.assertTrue(data["code"].startswith("RES-"))
        self.assertEqual(data.get("product_type"), "accommodation")
        self.assertIn("expires_at", data)

        code_obj = WhatsAppReservationCode.objects.get(code=data["code"])
        self.assertEqual(code_obj.accommodation_id, self.accommodation.id)
        self.assertIsNone(code_obj.experience_id)

    def test_post_accommodation_invalid_id_400(self):
        """Invalid/nonexistent accommodation_id → 400 with error message."""
        payload = {
            "accommodation_id": "00000000-0000-0000-0000-000000000000",
            "checkout_data": {},
        }
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_post_both_experience_and_accommodation_400(self):
        """Sending both experience_id and accommodation_id → 400."""
        payload = {
            "experience_id": "00000000-0000-0000-0000-000000000000",
            "accommodation_id": str(self.accommodation.id),
            "checkout_data": {},
        }
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400)


class ReservationByCodeAccommodationAPITests(TestCase):
    """GET /api/v1/whatsapp/reservation-by-code/ for accommodation."""

    def setUp(self):
        self.client = APIClient()
        self.base_url = "/api/v1/whatsapp/reservation-by-code/"
        self.accommodation = create_accommodation()
        self.message = create_whatsapp_message()

    def test_get_no_codigo_400(self):
        """Missing codigo query param → 400, error mentions 'codigo'."""
        response = self.client.get(self.base_url)
        self.assertEqual(response.status_code, 400)
        self.assertIn("codigo", response.json().get("error", "").lower())

    def test_get_code_not_found_404(self):
        """Nonexistent code → 404."""
        response = self.client.get(self.base_url, {"codigo": "RES-NONEXISTENT-00000000-XXXX"})
        self.assertEqual(response.status_code, 404)

    def test_get_code_expired_410(self):
        """Expired code → 410, error mentions 'expirado'."""
        code_obj = create_reservation_code_raw(
            code="RES-EXP-20250601-ABCD1234",
            accommodation=self.accommodation,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        response = self.client.get(self.base_url, {"codigo": code_obj.code})
        self.assertEqual(response.status_code, 410)
        self.assertIn("expirado", response.json().get("error", "").lower())

    def test_get_code_not_linked_409(self):
        """Code without linked_reservation → 409, error mentions 'vinculada'."""
        code_obj = create_reservation_code_for_accommodation(self.accommodation)
        self.assertIsNone(code_obj.linked_reservation_id)

        response = self.client.get(self.base_url, {"codigo": code_obj.code})
        self.assertEqual(response.status_code, 409)
        self.assertIn("vinculada", response.json().get("error", "").lower())

    def test_get_reservation_not_ready_for_payment_409(self):
        """Request status not ready for payment (e.g. operator_notified) → 409 with status in body."""
        code_obj = create_reservation_code_for_accommodation(self.accommodation)
        reservation = create_whatsapp_reservation_request(
            self.message,
            accommodation=self.accommodation,
            tour_code=code_obj.code,
            status="operator_notified",
        )
        code_obj.linked_reservation = reservation
        code_obj.save(update_fields=["linked_reservation"])

        response = self.client.get(self.base_url, {"codigo": code_obj.code})
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "operator_notified")

    def test_get_accommodation_ready_success(self):
        """Code + request availability_confirmed + linked_accommodation_reservation → 200, full payload, allow_payment true."""
        code_obj = create_reservation_code_for_accommodation(self.accommodation)
        reservation = create_whatsapp_reservation_request(
            self.message,
            accommodation=self.accommodation,
            tour_code=code_obj.code,
            status="availability_confirmed",
        )
        acc_res = create_accommodation_reservation(self.accommodation)
        reservation.linked_accommodation_reservation = acc_res
        reservation.save(update_fields=["linked_accommodation_reservation"])
        code_obj.linked_reservation = reservation
        code_obj.save(update_fields=["linked_reservation"])

        response = self.client.get(self.base_url, {"codigo": code_obj.code})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("product_type"), "accommodation")
        self.assertIsNotNone(data.get("accommodation"))
        self.assertEqual(data["accommodation"]["id"], str(self.accommodation.id))
        self.assertEqual(data.get("accommodation_reservation_id"), acc_res.reservation_id)
        self.assertIn("check_in", data)
        self.assertIn("check_out", data)
        self.assertIn("guests", data)
        self.assertIn("pricing", data)
        self.assertIn("customer", data)
        self.assertTrue(data.get("allow_payment"))

    def test_get_accommodation_already_paid_allow_payment_false(self):
        """When payment_received_at is set on the request → 200 with allow_payment false."""
        code_obj = create_reservation_code_for_accommodation(self.accommodation)
        reservation = create_whatsapp_reservation_request(
            self.message,
            accommodation=self.accommodation,
            tour_code=code_obj.code,
            status="availability_confirmed",
        )
        acc_res = create_accommodation_reservation(self.accommodation)
        reservation.linked_accommodation_reservation = acc_res
        reservation.payment_received_at = timezone.now()
        reservation.save(update_fields=["linked_accommodation_reservation", "payment_received_at"])
        code_obj.linked_reservation = reservation
        code_obj.save(update_fields=["linked_reservation"])

        response = self.client.get(self.base_url, {"codigo": code_obj.code})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json().get("allow_payment"))
