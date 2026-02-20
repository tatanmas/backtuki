"""
Tests for Superadmin Accommodations API: list, detail, PATCH gallery.

Enterprise: success, 401/403, 404, validation (invalid media_id, invalid room_category,
asset from other organizer), empty payload, sync gallery_media_ids.
"""
import io
import uuid
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accommodations.models import Accommodation
from apps.organizers.models import Organizer
from apps.media.models import MediaAsset

User = get_user_model()

BASE = "/api/v1/superadmin/accommodations"


def make_minimal_jpeg():
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), color="red").save(buf, format="JPEG")
        buf.seek(0)
        return buf.read()
    except Exception:
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


class SuperAdminAccommodationListTests(APITestCase):
    """GET /api/v1/superadmin/accommodations/"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.normal_user = User.objects.create_user(
            username="normal",
            email="normal@test.com",
            password="normpass123",
        )
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

    def test_list_requires_superuser(self):
        """Unauthenticated -> 401."""
        response = self.client.get(BASE + "/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_forbidden_for_normal_user(self):
        """Authenticated non-superuser -> 403."""
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(BASE + "/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_success_returns_results(self):
        """Superuser gets 200 and list of accommodations."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + "/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Test Cabin")
        self.assertEqual(response.data["results"][0]["photo_count"], 0)

    def test_list_filter_by_status(self):
        """Query param status filters."""
        Accommodation.objects.create(
            title="Draft Cabin",
            slug="draft-cabin",
            organizer=self.organizer,
            status="draft",
            guests=2,
            price=Decimal("30000"),
            currency="CLP",
        )
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + "/?status=published")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["status"], "published")


class SuperAdminAccommodationDetailTests(APITestCase):
    """GET /api/v1/superadmin/accommodations/<uuid>/"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
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

    def test_detail_requires_superuser(self):
        response = self.client.get(BASE + f"/{self.acc.id}/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_detail_404_invalid_uuid(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + "/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_success_includes_gallery_items_and_room_categories(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + f"/{self.acc.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Test Cabin")
        self.assertIn("gallery_items", response.data)
        self.assertIn("room_categories", response.data)
        self.assertIsInstance(response.data["gallery_items"], list)
        self.assertIsInstance(response.data["room_categories"], list)
        self.assertGreater(len(response.data["room_categories"]), 0)


class SuperAdminAccommodationGalleryPatchTests(APITestCase):
    """PATCH /api/v1/superadmin/accommodations/<uuid>/gallery/"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.organizer = Organizer.objects.create(name="Test Org", slug="test-org")
        self.other_organizer = Organizer.objects.create(name="Other Org", slug="other-org")
        self.acc = Accommodation.objects.create(
            title="Test Cabin",
            slug="test-cabin",
            organizer=self.organizer,
            status="published",
            guests=4,
            price=Decimal("50000"),
            currency="CLP",
        )
        jpeg = make_minimal_jpeg()
        self.asset = MediaAsset.objects.create(
            scope="organizer",
            organizer=self.organizer,
            original_filename="test.jpg",
            content_type="image/jpeg",
            size_bytes=len(jpeg),
            file=SimpleUploadedFile("test.jpg", jpeg, content_type="image/jpeg"),
        )

    def test_patch_requires_superuser(self):
        response = self.client.patch(
            BASE + f"/{self.acc.id}/gallery/",
            data={"gallery_items": [{"media_id": str(self.asset.id), "room_category": "sala", "sort_order": 0}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_400_missing_gallery_items(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(BASE + f"/{self.acc.id}/gallery/", data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("gallery_items", str(response.data).lower() or response.data.get("detail", ""))

    def test_patch_400_gallery_items_not_list(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/gallery/",
            data={"gallery_items": "not-a-list"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_400_invalid_media_id_uuid(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/gallery/",
            data={"gallery_items": [{"media_id": "not-a-uuid", "room_category": "sala", "sort_order": 0}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_400_media_asset_not_found(self):
        self.client.force_authenticate(user=self.superuser)
        fake_id = str(uuid.uuid4())
        response = self.client.patch(
            BASE + f"/{self.acc.id}/gallery/",
            data={"gallery_items": [{"media_id": fake_id, "room_category": "sala", "sort_order": 0}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_success_custom_room_category_allowed(self):
        """Custom room_category (e.g. custom place name) is allowed and stored."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/gallery/",
            data={"gallery_items": [{"media_id": str(self.asset.id), "room_category": "Terraza", "sort_order": 0}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gallery_items"][0]["room_category"], "Terraza")
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.gallery_items[0]["room_category"], "Terraza")

    def test_patch_success_updates_gallery_and_syncs_media_ids(self):
        self.client.force_authenticate(user=self.superuser)
        payload = {
            "gallery_items": [
                {"media_id": str(self.asset.id), "room_category": "sala", "sort_order": 0},
            ],
        }
        response = self.client.patch(BASE + f"/{self.acc.id}/gallery/", data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("gallery_items", response.data)
        self.assertEqual(len(response.data["gallery_items"]), 1)
        self.assertEqual(response.data["gallery_items"][0]["room_category"], "sala")
        self.assertEqual(response.data["photo_count"], 1)

        self.acc.refresh_from_db()
        self.assertEqual(self.acc.gallery_media_ids, [str(self.asset.id)])
        self.assertEqual(len(self.acc.gallery_items), 1)
        self.assertEqual(self.acc.gallery_items[0]["room_category"], "sala")

    def test_patch_success_empty_list_clears_gallery(self):
        self.acc.gallery_items = [{"media_id": str(self.asset.id), "room_category": "sala", "sort_order": 0}]
        self.acc.gallery_media_ids = [str(self.asset.id)]
        self.acc.save()
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/gallery/",
            data={"gallery_items": []},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["gallery_items"], [])
        self.assertEqual(response.data["photo_count"], 0)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.gallery_media_ids, [])
        self.assertEqual(self.acc.gallery_items, [])

    def test_patch_success_null_room_category(self):
        self.client.force_authenticate(user=self.superuser)
        payload = {
            "gallery_items": [
                {"media_id": str(self.asset.id), "room_category": None, "sort_order": 0},
            ],
        }
        response = self.client.patch(BASE + f"/{self.acc.id}/gallery/", data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.acc.refresh_from_db()
        self.assertIsNone(self.acc.gallery_items[0]["room_category"])

    def test_patch_400_asset_from_other_organizer(self):
        """MediaAsset belonging to another organizer is rejected."""
        jpeg = make_minimal_jpeg()
        other_asset = MediaAsset.objects.create(
            scope="organizer",
            organizer=self.other_organizer,
            original_filename="other.jpg",
            content_type="image/jpeg",
            size_bytes=len(jpeg),
            file=SimpleUploadedFile("other.jpg", jpeg, content_type="image/jpeg"),
        )
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/gallery/",
            data={"gallery_items": [{"media_id": str(other_asset.id), "room_category": "sala", "sort_order": 0}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
