"""
Tests for accommodation serializers: _resolve_images, _build_photo_tour, public dict with photo_tour.

Enterprise: edge cases (empty gallery, only gallery_media_ids, mixed categories, unclassified).
"""
import io
from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accommodations.models import Accommodation
from apps.accommodations.serializers import (
    _build_photo_tour,
    _accommodation_to_public_dict,
    PublicAccommodationDetailSerializer,
    PublicAccommodationListSerializer,
)
from apps.organizers.models import Organizer
from apps.media.models import MediaAsset


def make_minimal_jpeg():
    """Minimal valid JPEG bytes (1x1 pixel) for tests."""
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), color="red").save(buf, format="JPEG")
        buf.seek(0)
        return buf.read()
    except Exception:
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06Qa\x07\x13\x22q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfc\xbe\xe2\x8a(\xa2\x8a(\xa2\x8a(\xff\xd9"


class AccommodationSerializersTests(TestCase):
    """Test serializer helpers and public representation."""

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
        self.factory = RequestFactory()

    def test_build_photo_tour_empty_no_gallery(self):
        """Empty gallery_items and empty gallery_media_ids -> photo_tour []."""
        self.acc.gallery_items = []
        self.acc.gallery_media_ids = []
        self.acc.save()
        result = _build_photo_tour(self.acc)
        self.assertEqual(result, [])

    def test_build_photo_tour_empty_items_fallback_media_ids_empty(self):
        """Empty gallery_items but gallery_media_ids has IDs with no assets -> no URLs, so empty groups."""
        self.acc.gallery_items = []
        self.acc.gallery_media_ids = ["00000000-0000-0000-0000-000000000001"]
        self.acc.save()
        result = _build_photo_tour(self.acc)
        self.assertEqual(result, [])

    def test_build_photo_tour_with_one_asset(self):
        """One gallery_item with valid MediaAsset -> one section (or unclassified)."""
        jpeg = make_minimal_jpeg()
        f = SimpleUploadedFile("test.jpg", jpeg, content_type="image/jpeg")
        asset = MediaAsset.objects.create(
            scope="organizer",
            organizer=self.organizer,
            original_filename="test.jpg",
            content_type="image/jpeg",
            size_bytes=len(jpeg),
            file=f,
        )
        self.acc.gallery_items = [
            {"media_id": str(asset.id), "room_category": "sala", "sort_order": 0},
        ]
        self.acc.gallery_media_ids = [str(asset.id)]
        self.acc.save()
        result = _build_photo_tour(self.acc)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["room_category"], "sala")
        self.assertEqual(result[0]["label"], "Sala")
        self.assertEqual(len(result[0]["images"]), 1)
        self.assertTrue(result[0]["images"][0].startswith("http") or "/" in result[0]["images"][0])

    def test_build_photo_tour_unclassified_at_end(self):
        """room_category None -> unclassified section at end."""
        jpeg = make_minimal_jpeg()
        f = SimpleUploadedFile("uncl.jpg", jpeg, content_type="image/jpeg")
        asset = MediaAsset.objects.create(
            scope="organizer",
            organizer=self.organizer,
            original_filename="uncl.jpg",
            content_type="image/jpeg",
            size_bytes=len(jpeg),
            file=f,
        )
        self.acc.gallery_items = [
            {"media_id": str(asset.id), "room_category": None, "sort_order": 0},
        ]
        self.acc.gallery_media_ids = [str(asset.id)]
        self.acc.save()
        result = _build_photo_tour(self.acc)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["room_category"], "unclassified")
        self.assertEqual(result[0]["label"], "Sin clasificar")

    def test_accommodation_to_public_dict_includes_photo_tour_when_requested(self):
        """_accommodation_to_public_dict(include_photo_tour=True) adds photo_tour key."""
        data = _accommodation_to_public_dict(self.acc, include_photo_tour=True)
        self.assertIn("photo_tour", data)
        self.assertEqual(data["photo_tour"], [])

    def test_public_detail_serializer_includes_photo_tour(self):
        """PublicAccommodationDetailSerializer output has photo_tour."""
        serializer = PublicAccommodationDetailSerializer(self.acc, context={"request": None})
        data = serializer.data
        self.assertIn("photo_tour", data)
        self.assertIsInstance(data["photo_tour"], list)

    def test_public_list_serializer_no_photo_tour(self):
        """Public list does not include photo_tour (only detail)."""
        serializer = PublicAccommodationListSerializer(self.acc, context={"request": None})
        data = serializer.data
        self.assertNotIn("photo_tour", data)
        self.assertIn("images", data)
        self.assertEqual(data["images"], [])
