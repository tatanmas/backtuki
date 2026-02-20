"""
Tests for Creators landing slots: superadmin list/assign, MediaUsage.

Edge cases: auth, superuser, validation (slot_key empty/invalid), 404 (asset not found/deleted),
assign/unassign/reassign, empty body, invalid UUID.
"""
import io
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APITestCase
from rest_framework import status

from apps.creators.models import PlatformLandingSlot
from apps.media.models import MediaAsset, MediaUsage

User = get_user_model()

BASE_LIST = "/api/v1/superadmin/creators-landing-slots/"
BASE_ASSIGN = "/api/v1/superadmin/creators-landing-slots/assign/"

DEFAULT_SLOT_KEYS = ['creators_landing_hero', 'creators_landing_bento_1', 'creators_landing_bento_2']


def make_minimal_jpeg():
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), color="red").save(buf, format="JPEG")
        buf.seek(0)
        return buf.read()
    except Exception:
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def create_global_asset(filename="test.jpg"):
    """Create a global-scope MediaAsset for testing."""
    jpeg = make_minimal_jpeg()
    return MediaAsset.objects.create(
        scope="global",
        organizer=None,
        original_filename=filename,
        content_type="image/jpeg",
        size_bytes=len(jpeg),
        file=SimpleUploadedFile(filename, jpeg, content_type="image/jpeg"),
    )


class CreatorsLandingSlotsListApiTests(APITestCase):
    """GET /api/v1/superadmin/creators-landing-slots/"""

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

    def test_list_requires_auth(self):
        response = self.client.get(BASE_LIST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_requires_superuser(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(BASE_LIST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_success_returns_three_slots(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)
        keys = [item["slot_key"] for item in data]
        self.assertEqual(sorted(keys), sorted(DEFAULT_SLOT_KEYS))
        for item in data:
            self.assertIn("slot_key", item)
            self.assertIn("asset_id", item)
            self.assertIn("asset_url", item)
            self.assertIn("asset_filename", item)

    def test_list_creates_slots_if_missing(self):
        PlatformLandingSlot.objects.all().delete()
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(PlatformLandingSlot.objects.count(), 3)


class CreatorsLandingSlotsAssignApiTests(APITestCase):
    """PUT /api/v1/superadmin/creators-landing-slots/assign/"""

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
        self.asset = create_global_asset()

    def test_assign_requires_auth(self):
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "creators_landing_hero", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_assign_requires_superuser(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "creators_landing_hero", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_assign_400_empty_slot_key(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_400_missing_slot_key(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_400_invalid_slot_key(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "invalid_slot", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_404_asset_not_found(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "creators_landing_hero", "asset_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_assign_404_deleted_asset(self):
        self.asset.deleted_at = timezone.now()
        self.asset.save(update_fields=["deleted_at"])
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "creators_landing_hero", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_assign_invalid_uuid_returns_404(self):
        """Invalid UUID format should return 404, not 500."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "creators_landing_hero", "asset_id": "not-a-uuid"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_assign_success_creates_media_usage(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "creators_landing_hero", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["slot_key"], "creators_landing_hero")
        self.assertEqual(data["asset_id"], str(self.asset.id))
        self.assertIn("asset_url", data)

        slot = PlatformLandingSlot.objects.get(slot_key="creators_landing_hero")
        self.assertEqual(slot.asset_id, self.asset.id)

        slot_ct = ContentType.objects.get_for_model(PlatformLandingSlot)
        usages = MediaUsage.objects.filter(
            asset=self.asset,
            content_type=slot_ct,
            object_id=slot.id,
            deleted_at__isnull=True,
        )
        self.assertEqual(usages.count(), 1)
        self.assertEqual(usages.first().field_name, "slot_hero")

    def test_assign_null_unassigns_and_soft_deletes_usage(self):
        slot, _ = PlatformLandingSlot.objects.get_or_create(
            slot_key="creators_landing_hero",
            defaults={"asset_id": self.asset.id},
        )
        slot.asset = self.asset
        slot.save()
        slot_ct = ContentType.objects.get_for_model(PlatformLandingSlot)
        MediaUsage.objects.create(
            asset=self.asset,
            content_type=slot_ct,
            object_id=slot.id,
            field_name="slot_hero",
        )

        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "creators_landing_hero", "asset_id": None},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["asset_id"], None)

        slot.refresh_from_db()
        self.assertIsNone(slot.asset_id)

        active = MediaUsage.objects.filter(
            asset=self.asset,
            content_type=slot_ct,
            object_id=slot.id,
            deleted_at__isnull=True,
        )
        self.assertEqual(active.count(), 0)

    def test_assign_reassign_replaces_asset_and_usage(self):
        slot, _ = PlatformLandingSlot.objects.get_or_create(
            slot_key="creators_landing_hero",
            defaults={"asset_id": None},
        )
        slot.asset = self.asset
        slot.save()
        slot_ct = ContentType.objects.get_for_model(PlatformLandingSlot)
        MediaUsage.objects.create(
            asset=self.asset,
            content_type=slot_ct,
            object_id=slot.id,
            field_name="slot_hero",
        )
        new_asset = create_global_asset("other.jpg")

        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slot_key": "creators_landing_hero", "asset_id": str(new_asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        slot.refresh_from_db()
        self.assertEqual(slot.asset_id, new_asset.id)

        old_active = MediaUsage.objects.filter(
            asset=self.asset,
            content_type=slot_ct,
            object_id=slot.id,
            deleted_at__isnull=True,
        )
        self.assertEqual(old_active.count(), 0)

        new_active = MediaUsage.objects.filter(
            asset=new_asset,
            content_type=slot_ct,
            object_id=slot.id,
            deleted_at__isnull=True,
        )
        self.assertEqual(new_active.count(), 1)

    def test_assign_empty_body_400(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(BASE_ASSIGN, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CreatorsLandingSlotsMediaUsagesIntegrationTests(APITestCase):
    """Asset usages endpoint shows Creators slot usage."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.asset = create_global_asset()
        slot, _ = PlatformLandingSlot.objects.get_or_create(
            slot_key="creators_landing_hero",
            defaults={"asset_id": None},
        )
        slot.asset = self.asset
        slot.save()
        slot_ct = ContentType.objects.get_for_model(PlatformLandingSlot)
        MediaUsage.objects.create(
            asset=self.asset,
            content_type=slot_ct,
            object_id=slot.id,
            field_name="slot_hero",
        )

    def test_asset_usages_includes_creators_slot(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(f"/api/v1/media/assets/{self.asset.id}/usages/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["usage_count"], 1)
        self.assertEqual(len(data["usages"]), 1)
        usage = data["usages"][0]
        self.assertEqual(usage["field_name"], "slot_hero")
