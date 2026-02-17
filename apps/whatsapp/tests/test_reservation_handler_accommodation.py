"""
Tests for ReservationHandler (accommodation): confirm_availability,
_create_accommodation_reservation_if_needed, _create_and_link_accommodation_reservation, _build_payment_url.
Idempotency, invalid checkout_data, total 0.
"""
from django.test import TestCase
from unittest.mock import patch, MagicMock
from django.conf import settings

from apps.accommodations.models import AccommodationReservation
from apps.whatsapp.models import WhatsAppReservationCode, WhatsAppReservationRequest
from apps.whatsapp.services.reservation_handler import ReservationHandler
from core.testing import (
    create_accommodation,
    create_whatsapp_message,
    create_reservation_code_for_accommodation,
    create_reservation_code_raw,
    create_whatsapp_reservation_request,
)


class ReservationHandlerAccommodationTests(TestCase):
    """Confirm availability and create AccommodationReservation for accommodation flow."""

    def setUp(self):
        self.accommodation = create_accommodation()
        self.message = create_whatsapp_message(phone="+56912345678")
        self.code_obj = create_reservation_code_for_accommodation(self.accommodation)
        self.reservation = create_whatsapp_reservation_request(
            self.message,
            accommodation=self.accommodation,
            tour_code=self.code_obj.code,
            status="operator_notified",
        )
        self.code_obj.linked_reservation = self.reservation
        self.code_obj.save(update_fields=["linked_reservation"])

    @patch("apps.whatsapp.services.reservation_handler.WhatsAppWebService")
    @patch("apps.whatsapp.services.reservation_handler.GroupNotificationService.format_availability_confirmed_message")
    @patch("apps.whatsapp.services.reservation_handler.GroupNotificationService.format_payment_link_message")
    def test_confirm_availability_creates_accommodation_reservation_and_sends_link(
        self, mock_fmt_payment, mock_fmt_avail, mock_ws_class
    ):
        """confirm_availability → AccommodationReservation created, status availability_confirmed, payment_link with codigo."""
        mock_ws_class.return_value.send_message = MagicMock()
        mock_fmt_avail.return_value = "Availability confirmed."
        mock_fmt_payment.return_value = "Payment link: ..."

        ReservationHandler.confirm_availability(self.reservation)

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, "availability_confirmed")
        self.assertIsNotNone(self.reservation.payment_link)
        self.assertIn("checkout/accommodations/whatsapp", self.reservation.payment_link)
        self.assertIn("codigo=", self.reservation.payment_link)

        acc_res = AccommodationReservation.objects.filter(
            accommodation=self.accommodation
        ).first()
        self.assertIsNotNone(acc_res)
        self.assertEqual(acc_res.status, "pending")
        self.assertEqual(float(acc_res.total), 150000)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.linked_accommodation_reservation_id, acc_res.id)

    def test_create_accommodation_reservation_if_needed_idempotent(self):
        """When linked_accommodation_reservation already exists → _create_accommodation_reservation_if_needed returns False, no duplicate."""
        acc_res = ReservationHandler._create_and_link_accommodation_reservation(
            self.reservation, self.code_obj
        )
        self.assertIsNotNone(acc_res)
        first_id = acc_res.id

        created = ReservationHandler._create_accommodation_reservation_if_needed(self.reservation)
        self.assertFalse(created)

        count = AccommodationReservation.objects.filter(accommodation=self.accommodation).count()
        self.assertEqual(count, 1)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.linked_accommodation_reservation_id, first_id)

    def test_create_and_link_accommodation_reservation_invalid_dates_returns_none(self):
        """checkout_data with invalid check_in (not a date) → returns None, no AccommodationReservation created."""
        self.code_obj.checkout_data = {
            "check_in": "not-a-date",
            "check_out": "2025-06-03",
            "guests": 2,
            "pricing": {"total": 100000, "currency": "CLP"},
            "customer": {"first_name": "A", "last_name": "B", "email": "a@b.com"},
        }
        self.code_obj.save(update_fields=["checkout_data"])

        result = ReservationHandler._create_and_link_accommodation_reservation(
            self.reservation, self.code_obj
        )
        self.assertIsNone(result)
        self.assertEqual(AccommodationReservation.objects.filter(accommodation=self.accommodation).count(), 0)

    def test_create_and_link_accommodation_reservation_name_split(self):
        """customer with only 'name' (no first_name/last_name) → first/last name derived by split."""
        self.code_obj.checkout_data = {
            "check_in": "2025-06-01",
            "check_out": "2025-06-03",
            "guests": 2,
            "pricing": {"total": 50000, "currency": "CLP"},
            "customer": {"name": "María García", "email": "maria@example.com"},
        }
        self.code_obj.save(update_fields=["checkout_data"])

        result = ReservationHandler._create_and_link_accommodation_reservation(
            self.reservation, self.code_obj
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.first_name, "María")
        self.assertEqual(result.last_name, "García")

    def test_build_payment_url_accommodation(self):
        """_build_payment_url includes FRONTEND_URL, /checkout/accommodations/whatsapp, and codigo param."""
        url = ReservationHandler._build_payment_url(self.reservation)
        frontend = getattr(settings, "FRONTEND_URL", "http://localhost:8080").rstrip("/")
        self.assertTrue(url.startswith(frontend))
        self.assertIn("/checkout/accommodations/whatsapp", url)
        self.assertIn("codigo=", url)
        self.assertIn(self.code_obj.code, url)

    @patch("apps.whatsapp.services.reservation_handler.WhatsAppWebService")
    @patch("apps.whatsapp.services.reservation_handler.GroupNotificationService.format_availability_confirmed_message")
    def test_confirm_availability_total_zero_no_payment_link(self, mock_fmt_avail, mock_ws_class):
        """When checkout_data total is 0 → confirm_availability does not set payment_link (free stay)."""
        mock_ws_class.return_value.send_message = MagicMock()
        mock_fmt_avail.return_value = "Availability confirmed."
        self.code_obj.checkout_data = {
            "check_in": "2025-06-01",
            "check_out": "2025-06-03",
            "guests": 2,
            "pricing": {"total": 0, "currency": "CLP"},
            "customer": {"first_name": "A", "last_name": "B", "email": "a@b.com"},
        }
        self.code_obj.save(update_fields=["checkout_data"])

        ReservationHandler.confirm_availability(self.reservation)

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, "availability_confirmed")
        self.assertFalse(self.reservation.payment_link)

    def test_create_and_link_accommodation_reservation_name_single_word(self):
        """customer with single-word 'name' → first_name set, last_name empty string."""
        self.code_obj.checkout_data = {
            "check_in": "2025-06-01",
            "check_out": "2025-06-03",
            "guests": 2,
            "pricing": {"total": 50000, "currency": "CLP"},
            "customer": {"name": "Juan", "email": "juan@example.com"},
        }
        self.code_obj.save(update_fields=["checkout_data"])

        result = ReservationHandler._create_and_link_accommodation_reservation(
            self.reservation, self.code_obj
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.first_name, "Juan")
        self.assertEqual(result.last_name, "")
