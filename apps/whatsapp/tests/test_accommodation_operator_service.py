"""
Tests for AccommodationOperatorService (group/operator resolution).

Enterprise, simple: one file, focused on get_accommodation_whatsapp_group.
"""
from django.test import TestCase
from decimal import Decimal

from apps.accommodations.models import Accommodation
from apps.organizers.models import Organizer
from apps.whatsapp.models import TourOperator, AccommodationOperatorBinding, AccommodationGroupBinding, WhatsAppChat
from apps.whatsapp.services.accommodation_operator_service import AccommodationOperatorService


class AccommodationOperatorServiceTests(TestCase):
    """Test get_accommodation_whatsapp_group with bindings."""

    def setUp(self):
        self.organizer = Organizer.objects.create(name="Test Org", slug="test-org")
        self.accommodation = Accommodation.objects.create(
            title="Test Cabin",
            slug="test-cabin",
            organizer=self.organizer,
            status="published",
            guests=4,
            price=Decimal("50000"),
            currency="CLP",
        )

    def test_get_accommodation_whatsapp_group_no_bindings_returns_none(self):
        result = AccommodationOperatorService.get_accommodation_whatsapp_group(self.accommodation)
        self.assertIsNone(result)

    def test_get_accommodation_whatsapp_group_with_operator_and_default_group(self):
        group = WhatsAppChat.objects.create(
            chat_id="120363000000@g.us",
            name="Test Group",
            type="group",
        )
        operator = TourOperator.objects.create(
            name="Test Operator",
            default_whatsapp_group=group,
        )
        AccommodationOperatorBinding.objects.create(
            accommodation=self.accommodation,
            tour_operator=operator,
            is_active=True,
        )
        result = AccommodationOperatorService.get_accommodation_whatsapp_group(self.accommodation)
        self.assertIsNotNone(result)
        self.assertEqual(result["chat_id"], group.chat_id)
        self.assertEqual(result["source"], "operator_default")
        self.assertEqual(result["operator"], operator)
