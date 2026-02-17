"""
Tests for reservation code generation (accommodation flow).

Enterprise, simple: one file, focused on ReservationCodeGenerator for accommodations.
"""
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.accommodations.models import Accommodation
from apps.organizers.models import Organizer
from apps.whatsapp.models import WhatsAppReservationCode
from apps.whatsapp.services.reservation_code_generator import ReservationCodeGenerator
from core.testing.fixtures import CHECKOUT_DATA_ACCOMMODATION_MINIMAL, CHECKOUT_DATA_ACCOMMODATION_FULL


class ReservationCodeAccommodationTests(TestCase):
    """Test generate_code_for_accommodation and code shape."""

    def setUp(self):
        self.organizer = Organizer.objects.create(
            name="Test Org",
            slug="test-org",
        )
        self.accommodation = Accommodation.objects.create(
            title="Test Cabin",
            slug="test-cabin",
            organizer=self.organizer,
            status="published",
            guests=4,
            price=Decimal("50000"),
            currency="CLP",
        )

    def test_generate_code_for_accommodation_creates_code(self):
        """Valid accommodation_id + checkout_data → code created with accommodation set, experience null, status pending."""
        checkout_data = {
            "check_in": "2025-03-01",
            "check_out": "2025-03-03",
            "guests": 2,
            "pricing": {"total": 100000, "currency": "CLP"},
            "customer": {"name": "Test User"},
        }
        code_obj = ReservationCodeGenerator.generate_code_for_accommodation(
            str(self.accommodation.id), checkout_data
        )
        self.assertIsNotNone(code_obj)
        self.assertEqual(code_obj.accommodation_id, self.accommodation.id)
        self.assertIsNone(code_obj.experience_id)
        self.assertEqual(code_obj.checkout_data["check_in"], "2025-03-01")
        self.assertEqual(code_obj.checkout_data["guests"], 2)
        self.assertTrue(code_obj.code.startswith("RES-"))
        self.assertEqual(code_obj.status, "pending")

    def test_generate_code_for_accommodation_invalid_id_raises(self):
        """Nonexistent accommodation_id → ValueError with 'not found'."""
        with self.assertRaises(ValueError) as ctx:
            ReservationCodeGenerator.generate_code_for_accommodation(
                "00000000-0000-0000-0000-000000000000", {}
            )
        self.assertIn("not found", str(ctx.exception).lower())

    def test_generate_code_for_accommodation_full_checkout_data(self):
        """Full checkout_data (pricing, contact) → code has correct data and future expires_at."""
        code_obj = ReservationCodeGenerator.generate_code_for_accommodation(
            str(self.accommodation.id), CHECKOUT_DATA_ACCOMMODATION_FULL.copy()
        )
        self.assertIsNotNone(code_obj)
        self.assertEqual(code_obj.accommodation_id, self.accommodation.id)
        self.assertEqual(code_obj.checkout_data["pricing"]["total"], 150000)
        self.assertIsNotNone(code_obj.expires_at)
        self.assertGreater(code_obj.expires_at, timezone.now())

    def test_validate_code_returns_none_for_expired(self):
        """Code with expires_at in the past → validate_code returns None."""
        code_obj = ReservationCodeGenerator.generate_code_for_accommodation(
            str(self.accommodation.id), CHECKOUT_DATA_ACCOMMODATION_MINIMAL.copy()
        )
        code_obj.expires_at = timezone.now() - timedelta(minutes=1)
        code_obj.save(update_fields=["expires_at"])
        result = ReservationCodeGenerator.validate_code(code_obj.code)
        self.assertIsNone(result)

    def test_validate_code_returns_none_for_non_pending_status(self):
        """Code with status != 'pending' (e.g. linked) → validate_code returns None."""
        code_obj = ReservationCodeGenerator.generate_code_for_accommodation(
            str(self.accommodation.id), CHECKOUT_DATA_ACCOMMODATION_MINIMAL.copy()
        )
        code_obj.status = "linked"
        code_obj.save(update_fields=["status"])
        result = ReservationCodeGenerator.validate_code(code_obj.code)
        self.assertIsNone(result)

    def test_validate_code_returns_code_when_valid(self):
        """Valid pending code → validate_code returns the code object."""
        code_obj = ReservationCodeGenerator.generate_code_for_accommodation(
            str(self.accommodation.id), CHECKOUT_DATA_ACCOMMODATION_MINIMAL.copy()
        )
        result = ReservationCodeGenerator.validate_code(code_obj.code)
        self.assertIsNotNone(result)
        self.assertEqual(result.id, code_obj.id)
