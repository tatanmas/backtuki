"""
Tests for PlatformFlow creation when creating experience/accommodation reservations via WhatsApp.
ReservationHandler._create_and_link_experience_reservation and _create_and_link_accommodation_reservation
should create PlatformFlow (experience_booking / accommodation_booking) and RESERVATION_CREATED event.
"""
from django.test import TestCase

from core.models import PlatformFlow, PlatformFlowEvent
from apps.accommodations.models import AccommodationReservation
from apps.whatsapp.models import WhatsAppReservationCode, WhatsAppReservationRequest
from apps.whatsapp.services.reservation_handler import ReservationHandler
from core.testing import (
    create_accommodation,
    create_whatsapp_message,
    create_reservation_code_for_accommodation,
    create_whatsapp_reservation_request,
)


class WhatsAppAccommodationFlowTests(TestCase):
    """Creating accommodation reservation via WhatsApp creates accommodation_booking PlatformFlow and RESERVATION_CREATED."""

    def setUp(self):
        self.accommodation = create_accommodation()
        self.message = create_whatsapp_message(phone="+56987654321")
        self.code_obj = create_reservation_code_for_accommodation(self.accommodation)
        self.reservation = create_whatsapp_reservation_request(
            self.message,
            accommodation=self.accommodation,
            tour_code=self.code_obj.code,
            status="operator_notified",
        )
        self.code_obj.linked_reservation = self.reservation
        self.code_obj.save(update_fields=["linked_reservation"])

    def test_create_and_link_accommodation_reservation_creates_platform_flow(self):
        """_create_and_link_accommodation_reservation creates PlatformFlow accommodation_booking and RESERVATION_CREATED event."""
        initial_flows = set(PlatformFlow.objects.values_list("id", flat=True))

        result = ReservationHandler._create_and_link_accommodation_reservation(
            self.reservation, self.code_obj
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result, AccommodationReservation)

        new_flows = PlatformFlow.objects.exclude(id__in=initial_flows)
        self.assertEqual(new_flows.count(), 1)
        flow = new_flows.get()
        self.assertEqual(flow.flow_type, "accommodation_booking")
        self.assertEqual(flow.accommodation_id, self.accommodation.id)
        self.assertEqual(flow.metadata.get("source"), "whatsapp")
        self.assertIn("reservation_id", flow.metadata)

        events = list(flow.events.values_list("step", flat=True))
        self.assertIn("RESERVATION_CREATED", events)
