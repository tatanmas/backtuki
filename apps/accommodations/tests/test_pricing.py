"""
Tests for accommodation pricing service (cobros adicionales v1.5).
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accommodations.models import Accommodation, AccommodationExtraCharge
from apps.accommodations.services.pricing import (
    calculate_accommodation_pricing,
    AccommodationPricingError,
)
from apps.organizers.models import Organizer


class AccommodationPricingServiceTests(TestCase):
    def setUp(self):
        self.organizer = Organizer.objects.create(name="Test Org", slug="test-org")
        self.acc = Accommodation.objects.create(
            title="Test Cabin",
            slug="test-cabin",
            organizer=self.organizer,
            status="published",
            guests=4,
            bedrooms=2,
            full_bathrooms=2,
            half_bathrooms=0,
            beds=3,
            price=Decimal("90000"),
            currency="CLP",
        )

    def test_base_only_no_extras(self):
        """Base subtotal = nights × price_per_night; no extras."""
        snapshot = calculate_accommodation_pricing(
            accommodation_id=self.acc.id,
            check_in=date(2025, 4, 1),
            check_out=date(2025, 4, 5),
            guests=2,
            selected_options=[],
        )
        self.assertEqual(snapshot["snapshot_version"], 1)
        self.assertEqual(snapshot["nights"], 4)
        self.assertEqual(snapshot["currency"], "CLP")
        self.assertEqual(snapshot["base"]["price_per_night"], 90000.0)
        self.assertEqual(snapshot["base"]["subtotal"], 360000.0)
        self.assertEqual(snapshot["extras"], [])
        self.assertEqual(snapshot["total"], 360000.0)

    def test_with_mandatory_per_stay_extra(self):
        """Mandatory per_stay extra adds one-time amount."""
        AccommodationExtraCharge.objects.create(
            accommodation=self.acc,
            code="cleaning",
            name="Limpieza final",
            charge_type="per_stay",
            amount=Decimal("25000"),
            is_optional=False,
            is_active=True,
            display_order=0,
        )
        snapshot = calculate_accommodation_pricing(
            accommodation_id=self.acc.id,
            check_in=date(2025, 4, 1),
            check_out=date(2025, 4, 5),
            guests=2,
            selected_options=[],
        )
        self.assertEqual(snapshot["nights"], 4)
        self.assertEqual(snapshot["base"]["subtotal"], 360000.0)
        self.assertEqual(len(snapshot["extras"]), 1)
        self.assertEqual(snapshot["extras"][0]["code"], "cleaning")
        self.assertEqual(snapshot["extras"][0]["quantity"], 1)
        self.assertEqual(snapshot["extras"][0]["total"], 25000.0)
        self.assertEqual(snapshot["total"], 385000.0)

    def test_with_mandatory_per_night_extra(self):
        """Mandatory per_night extra adds amount × nights."""
        AccommodationExtraCharge.objects.create(
            accommodation=self.acc,
            code="resort_fee",
            name="Tarifa resort",
            charge_type="per_night",
            amount=Decimal("5000"),
            is_optional=False,
            is_active=True,
            display_order=0,
        )
        snapshot = calculate_accommodation_pricing(
            accommodation_id=self.acc.id,
            check_in=date(2025, 4, 1),
            check_out=date(2025, 4, 5),
            guests=2,
            selected_options=[],
        )
        self.assertEqual(snapshot["extras"][0]["quantity"], 4)
        self.assertEqual(snapshot["extras"][0]["total"], 20000.0)
        self.assertEqual(snapshot["total"], 380000.0)

    def test_with_optional_extra_from_selected_options(self):
        """Optional extra from selected_options with quantity."""
        AccommodationExtraCharge.objects.create(
            accommodation=self.acc,
            code="linens",
            name="Ropa de cama",
            charge_type="per_stay",
            amount=Decimal("15000"),
            is_optional=True,
            is_active=True,
            max_quantity=4,
            display_order=0,
        )
        snapshot = calculate_accommodation_pricing(
            accommodation_id=self.acc.id,
            check_in=date(2025, 4, 1),
            check_out=date(2025, 4, 5),
            guests=2,
            selected_options=[{"code": "linens", "quantity": 2}],
        )
        self.assertEqual(len(snapshot["extras"]), 1)
        self.assertEqual(snapshot["extras"][0]["code"], "linens")
        self.assertEqual(snapshot["extras"][0]["quantity"], 2)
        self.assertEqual(snapshot["extras"][0]["total"], 30000.0)
        self.assertEqual(snapshot["total"], 390000.0)

    def test_invalid_extra_code_raises(self):
        """Invalid or non-optional code in selected_options raises AccommodationPricingError."""
        AccommodationExtraCharge.objects.create(
            accommodation=self.acc,
            code="cleaning",
            name="Limpieza",
            charge_type="per_stay",
            amount=Decimal("25000"),
            is_optional=False,
            is_active=True,
        )
        with self.assertRaises(AccommodationPricingError):
            calculate_accommodation_pricing(
                accommodation_id=self.acc.id,
                check_in=date(2025, 4, 1),
                check_out=date(2025, 4, 5),
                guests=2,
                selected_options=[{"code": "cleaning", "quantity": 1}],
            )

    def test_inactive_extra_in_selected_options_raises(self):
        """Inactive optional extra in selected_options raises."""
        AccommodationExtraCharge.objects.create(
            accommodation=self.acc,
            code="linens",
            name="Ropa de cama",
            charge_type="per_stay",
            amount=Decimal("15000"),
            is_optional=True,
            is_active=False,
        )
        with self.assertRaises(AccommodationPricingError):
            calculate_accommodation_pricing(
                accommodation_id=self.acc.id,
                check_in=date(2025, 4, 1),
                check_out=date(2025, 4, 5),
                guests=2,
                selected_options=[{"code": "linens", "quantity": 1}],
            )

    def test_quantity_exceeds_max_quantity_raises(self):
        """quantity > max_quantity raises AccommodationPricingError."""
        AccommodationExtraCharge.objects.create(
            accommodation=self.acc,
            code="linens",
            name="Ropa de cama",
            charge_type="per_stay",
            amount=Decimal("15000"),
            is_optional=True,
            is_active=True,
            max_quantity=2,
        )
        with self.assertRaises(AccommodationPricingError):
            calculate_accommodation_pricing(
                accommodation_id=self.acc.id,
                check_in=date(2025, 4, 1),
                check_out=date(2025, 4, 5),
                guests=2,
                selected_options=[{"code": "linens", "quantity": 5}],
            )

    def test_check_out_before_check_in_raises(self):
        """check_out <= check_in raises."""
        with self.assertRaises(AccommodationPricingError):
            calculate_accommodation_pricing(
                accommodation_id=self.acc.id,
                check_in=date(2025, 4, 5),
                check_out=date(2025, 4, 1),
                guests=2,
                selected_options=[],
            )

    def test_min_nights_not_met_raises(self):
        """Fewer nights than min_nights raises."""
        self.acc.min_nights = 3
        self.acc.save()
        with self.assertRaises(AccommodationPricingError):
            calculate_accommodation_pricing(
                accommodation_id=self.acc.id,
                check_in=date(2025, 4, 1),
                check_out=date(2025, 4, 2),
                guests=2,
                selected_options=[],
            )

    def test_string_dates_accepted(self):
        """check_in/check_out as ISO strings work."""
        snapshot = calculate_accommodation_pricing(
            accommodation_id=self.acc.id,
            check_in="2025-04-01",
            check_out="2025-04-05",
            guests=2,
            selected_options=[],
        )
        self.assertEqual(snapshot["nights"], 4)
        self.assertEqual(snapshot["total"], 360000.0)
