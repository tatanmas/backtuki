"""
Tests for ReservationCodeProcessor (accommodation flow): process_code, _process_accommodation.
Edge cases: already linked, expired, code not found, no operator/group.
"""
from django.test import TestCase
from unittest.mock import patch, MagicMock
from django.utils import timezone
from datetime import timedelta

from apps.whatsapp.models import WhatsAppReservationCode, WhatsAppReservationRequest
from apps.whatsapp.services.reservation_code_processor import ReservationCodeProcessor
from core.testing import (
    create_accommodation,
    create_whatsapp_message,
    create_reservation_code_raw,
    create_reservation_code_for_accommodation,
    create_whatsapp_chat,
    create_tour_operator,
    create_accommodation_operator_binding,
)


class ReservationCodeProcessorAccommodationTests(TestCase):
    """Process accommodation reservation codes."""

    def setUp(self):
        self.accommodation = create_accommodation()
        self.message = create_whatsapp_message(content="RES-ABC")

    def test_process_code_accommodation_creates_request_and_links(self):
        """Valid RES-* code → WhatsAppReservationRequest created, code.linked_reservation set."""
        code_obj = create_reservation_code_for_accommodation(self.accommodation)
        self.message.content = code_obj.code
        self.message.save(update_fields=["content"])

        with patch(
            "apps.whatsapp.services.accommodation_operator_service.AccommodationOperatorService.get_accommodation_whatsapp_group"
        ) as mock_group:
            mock_group.return_value = None

            with patch(
                "apps.whatsapp.services.reservation_code_processor.GroupNotificationService.send_reservation_notification"
            ):
                with patch(
                    "apps.whatsapp.services.reservation_code_processor.WhatsAppWebService"
                ) as mock_ws:
                    mock_ws.return_value.send_message = MagicMock()

                    result = ReservationCodeProcessor.process(self.message, code_obj.code)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, WhatsAppReservationRequest)
        self.assertEqual(result.accommodation_id, self.accommodation.id)
        self.assertIsNone(result.experience_id)
        code_obj.refresh_from_db()
        self.assertEqual(code_obj.linked_reservation_id, result.id)

    def test_process_code_already_linked_returns_existing(self):
        """Code already has linked_reservation → returns existing request, no duplicate created."""
        code_obj = create_reservation_code_for_accommodation(self.accommodation)
        existing = WhatsAppReservationRequest.objects.create(
            whatsapp_message=self.message,
            tour_code=code_obj.code,
            passengers=2,
            accommodation=self.accommodation,
            status="operator_notified",
            timeout_at=timezone.now() + timedelta(minutes=30),
        )
        code_obj.linked_reservation = existing
        code_obj.save(update_fields=["linked_reservation"])
        self.message.content = code_obj.code
        self.message.save(update_fields=["content"])

        result = ReservationCodeProcessor.process(self.message, code_obj.code)

        self.assertIsNotNone(result)
        self.assertEqual(result.id, existing.id)
        self.assertEqual(WhatsAppReservationRequest.objects.filter(accommodation=self.accommodation).count(), 1)

    def test_process_code_expired_returns_none(self):
        """Expired code → process returns None, linked_reservation stays null."""
        code_obj = create_reservation_code_raw(
            code="RES-EXP-20250601-ABCD1234",
            accommodation=self.accommodation,
            status="pending",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.message.content = code_obj.code
        self.message.save(update_fields=["content"])

        result = ReservationCodeProcessor.process(self.message, code_obj.code)

        self.assertIsNone(result)
        self.assertIsNone(WhatsAppReservationCode.objects.get(code=code_obj.code).linked_reservation_id)

    def test_process_code_not_found_returns_none(self):
        """Nonexistent code string → process returns None (DoesNotExist handled)."""
        result = ReservationCodeProcessor.process(self.message, "RES-NONEXISTENT-00000000-XXXX")
        self.assertIsNone(result)

    def test_process_code_with_operator_notifies_group(self):
        """Accommodation with operator binding → mark_operator_notified called, request linked."""
        group = create_whatsapp_chat()
        operator = create_tour_operator(default_whatsapp_group=group)
        create_accommodation_operator_binding(self.accommodation, operator)
        code_obj = create_reservation_code_for_accommodation(self.accommodation)
        self.message.content = code_obj.code
        self.message.save(update_fields=["content"])

        with patch(
            "apps.whatsapp.services.reservation_code_processor.ReservationHandler.mark_operator_notified"
        ) as mock_mark:
            with patch(
                "apps.whatsapp.services.reservation_code_processor.WhatsAppWebService"
            ) as mock_ws:
                mock_ws.return_value.send_message = MagicMock()

                result = ReservationCodeProcessor.process(self.message, code_obj.code)

        self.assertIsNotNone(result)
        mock_mark.assert_called_once()
        code_obj.refresh_from_db()
        self.assertEqual(code_obj.linked_reservation_id, result.id)
