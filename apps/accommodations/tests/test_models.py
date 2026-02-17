"""
Tests for accommodation models (Accommodation, AccommodationReservation).

Enterprise, simple: model creation, basic fields, gallery_items (photo tour).
"""
from decimal import Decimal
from django.test import TestCase

from datetime import date

from apps.accommodations.models import Accommodation, AccommodationReservation, AccommodationReview
from apps.accommodations.constants import ROOM_CATEGORIES, ROOM_CATEGORY_LABELS
from apps.organizers.models import Organizer


class AccommodationModelTests(TestCase):
    """Test Accommodation and AccommodationReservation creation."""

    def setUp(self):
        self.organizer = Organizer.objects.create(name="Test Org", slug="test-org")
        self.acc = Accommodation.objects.create(
            title="Test Cabin",
            slug="test-cabin",
            organizer=self.organizer,
            status="published",
            guests=4,
            bedrooms=2,
            bathrooms=2,
            beds=3,
            price=Decimal("50000"),
            currency="CLP",
        )

    def test_accommodation_review_creation(self):
        """AccommodationReview created and linked to accommodation; acc.reviews.count() == 1."""
        review = AccommodationReview.objects.create(
            accommodation=self.acc,
            author_name="María G.",
            author_location="Santiago",
            rating=5,
            text="Excelente cabaña, muy limpia.",
            review_date=date(2025, 2, 1),
            stay_type="Estadía de varias noches",
            host_reply="Gracias por tu comentario.",
        )
        self.assertEqual(review.accommodation, self.acc)
        self.assertEqual(review.rating, 5)
        self.assertIn("reviews", dir(self.acc))
        self.assertEqual(self.acc.reviews.count(), 1)

    def test_accommodation_reservation_creation(self):
        """AccommodationReservation with reservation_id, dates, guests, total persists correctly."""
        res = AccommodationReservation.objects.create(
            reservation_id="ACC-TEST12345678",
            accommodation=self.acc,
            status="pending",
            check_in=date(2025, 3, 1),
            check_out=date(2025, 3, 3),
            guests=2,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            phone="+56912345678",
            total=Decimal("100000"),
            currency="CLP",
        )
        self.assertEqual(res.accommodation, self.acc)
        self.assertEqual(res.status, "pending")
        self.assertEqual(res.guests, 2)
        self.assertEqual(res.reservation_id, "ACC-TEST12345678")

    def test_gallery_items_default_empty(self):
        """New accommodation has gallery_items = [] and gallery_media_ids = []."""
        self.assertEqual(self.acc.gallery_items, [])
        self.assertEqual(self.acc.gallery_media_ids, [])

    def test_gallery_items_save_and_load(self):
        """gallery_items persists and accepts valid structure (media_id, room_category, sort_order)."""
        self.acc.gallery_items = [
            {"media_id": "a1b2c3d4-0000-4000-8000-000000000001", "room_category": "sala", "sort_order": 0},
            {"media_id": "a1b2c3d4-0000-4000-8000-000000000002", "room_category": None, "sort_order": 1},
        ]
        self.acc.save()
        self.acc.refresh_from_db()
        self.assertEqual(len(self.acc.gallery_items), 2)
        self.assertEqual(self.acc.gallery_items[0]["room_category"], "sala")
        self.assertIsNone(self.acc.gallery_items[1]["room_category"])

    def test_constants_room_categories(self):
        """ROOM_CATEGORIES and ROOM_CATEGORY_LABELS are consistent."""
        self.assertEqual(len(ROOM_CATEGORIES), 6)
        for value, label in ROOM_CATEGORIES:
            self.assertEqual(ROOM_CATEGORY_LABELS.get(value), label)
        self.assertIn(("sala", "Sala"), ROOM_CATEGORIES)
        self.assertIn(("bano", "Baño completo"), ROOM_CATEGORIES)
