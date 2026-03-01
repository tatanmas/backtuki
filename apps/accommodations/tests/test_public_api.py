"""
Tests for public accommodations API: list, detail, photo_tour in detail.

List: published only. Detail: published or draft (draft = unlisted, accessible by direct link).
404 for slug/id not found; photo_tour present when categorized.
"""
import io
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accommodations.models import Accommodation, AccommodationReview
from apps.organizers.models import Organizer
from apps.media.models import MediaAsset

BASE = "/api/v1/accommodations/public"


def make_minimal_jpeg():
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), color="red").save(buf, format="JPEG")
        buf.seek(0)
        return buf.read()
    except Exception:
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


class PublicAccommodationListTests(APITestCase):
    """GET /api/v1/accommodations/public/"""

    def setUp(self):
        self.organizer = Organizer.objects.create(name="Test Org", slug="test-org")
        Accommodation.objects.create(
            title="Published Cabin",
            slug="published-cabin",
            organizer=self.organizer,
            status="published",
            guests=4,
            price=Decimal("50000"),
            currency="CLP",
        )
        Accommodation.objects.create(
            title="Draft Cabin",
            slug="draft-cabin",
            organizer=self.organizer,
            status="draft",
            guests=2,
            price=Decimal("30000"),
            currency="CLP",
        )

    def test_list_returns_only_published(self):
        response = self.client.get(BASE + "/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Published Cabin")

    def test_list_unauthenticated_ok(self):
        response = self.client.get(BASE + "/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PublicAccommodationDetailTests(APITestCase):
    """GET /api/v1/accommodations/public/<slug_or_id>/"""

    def setUp(self):
        self.organizer = Organizer.objects.create(name="Test Org", slug="test-org")
        self.acc = Accommodation.objects.create(
            title="Test Cabin",
            slug="test-cabin",
            organizer=self.organizer,
            status="published",
            guests=4,
            price=Decimal("50000"),
            currency="CLP",
        )

    def test_detail_by_slug_success(self):
        response = self.client.get(BASE + "/test-cabin/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Test Cabin")
        self.assertIn("images", response.data)
        self.assertIn("photo_tour", response.data)
        self.assertIsInstance(response.data["photo_tour"], list)

    def test_detail_by_id_success(self):
        response = self.client.get(BASE + f"/{self.acc.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.acc.id))

    def test_detail_accessible_when_draft_unlisted(self):
        """Draft accommodations are not in the list but are accessible by direct link (unlisted)."""
        Accommodation.objects.create(
            title="Draft Only",
            slug="draft-only",
            organizer=self.organizer,
            status="draft",
            guests=2,
            price=Decimal("20000"),
            currency="CLP",
        )
        response = self.client.get(BASE + "/draft-only/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Draft Only")
        self.assertEqual(response.data["slug"], "draft-only")

    def test_detail_404_invalid_slug(self):
        response = self.client.get(BASE + "/nonexistent-slug-12345/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_photo_tour_when_gallery_items_categorized(self):
        """When accommodation has gallery_items with room_category, detail includes photo_tour with sections."""
        jpeg = make_minimal_jpeg()
        asset = MediaAsset.objects.create(
            scope="organizer",
            organizer=self.organizer,
            original_filename="test.jpg",
            content_type="image/jpeg",
            size_bytes=len(jpeg),
            file=SimpleUploadedFile("test.jpg", jpeg, content_type="image/jpeg"),
        )
        self.acc.gallery_items = [
            {"media_id": str(asset.id), "room_category": "sala", "sort_order": 0},
        ]
        self.acc.gallery_media_ids = [str(asset.id)]
        self.acc.save()

        response = self.client.get(BASE + "/test-cabin/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("photo_tour", response.data)
        self.assertIsInstance(response.data["photo_tour"], list)
        self.assertGreaterEqual(len(response.data["photo_tour"]), 1)
        self.assertEqual(response.data["photo_tour"][0]["room_category"], "sala")
        self.assertEqual(response.data["photo_tour"][0]["label"], "Sala")
        self.assertEqual(len(response.data["photo_tour"][0]["images"]), 1)

    def test_detail_includes_reviews_list(self):
        """When accommodation has reviews, public detail includes reviewsList with author_name, rating, text."""
        AccommodationReview.objects.create(
            accommodation=self.acc,
            author_name="Juan P.",
            author_location="Valparaíso",
            rating=4,
            text="Muy buena estadía.",
            stay_type="Estadía de varias noches",
        )
        response = self.client.get(BASE + "/test-cabin/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("reviewsList", response.data)
        self.assertIsInstance(response.data["reviewsList"], list)
        self.assertEqual(len(response.data["reviewsList"]), 1)
        self.assertEqual(response.data["reviewsList"][0]["author_name"], "Juan P.")
        self.assertEqual(response.data["reviewsList"][0]["rating"], 4)
        self.assertEqual(response.data["reviewsList"][0]["text"], "Muy buena estadía.")
