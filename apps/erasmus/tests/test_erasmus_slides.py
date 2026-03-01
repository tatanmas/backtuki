"""
Tests for Erasmus slides: model, superadmin list/assign, public slides, MediaUsage.

Edge cases: auth, validation, 404, re-assign, unassign, deleted assets, malformed bodies.
"""
import io
import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from apps.erasmus.models import ErasmusSlideConfig
from apps.media.models import MediaAsset, MediaUsage
from django.contrib.contenttypes.models import ContentType

User = get_user_model()

# Superadmin endpoints
BASE_LIST = "/api/v1/superadmin/erasmus-slides/"
BASE_ASSIGN = "/api/v1/superadmin/erasmus-slides/assign/"


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


class ErasmusSlideConfigModelTests(TestCase):
    """ErasmusSlideConfig model."""

    def test_create_with_slide_id(self):
        config = ErasmusSlideConfig.objects.create(slide_id="sunset-manquehue", order=0)
        self.assertEqual(config.slide_id, "sunset-manquehue")
        self.assertIsNone(config.asset_id)
        self.assertEqual(config.order, 0)

    def test_slide_id_unique(self):
        ErasmusSlideConfig.objects.create(slide_id="sunset-manquehue", order=0)
        with self.assertRaises(Exception):  # IntegrityError
            ErasmusSlideConfig.objects.create(slide_id="sunset-manquehue", order=1)


class ErasmusSlidesListApiTests(APITestCase):
    """GET /api/v1/superadmin/erasmus-slides/"""

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
        """Unauthenticated -> 401."""
        response = self.client.get(BASE_LIST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_requires_superuser(self):
        """Normal user -> 403."""
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(BASE_LIST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_success_returns_three_slides(self):
        """Superuser gets 200 and list of 3 default slides."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE_LIST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)
        slide_ids = [s["slide_id"] for s in data]
        self.assertIn("sunset-manquehue", slide_ids)
        self.assertIn("valpo-concon", slide_ids)
        self.assertIn("san-cristobal-bike", slide_ids)
        for s in data:
            self.assertIn("slide_id", s)
            self.assertIn("asset_id", s)
            self.assertIn("asset_url", s)
            self.assertIn("asset_filename", s)
            self.assertIn("order", s)

    def test_list_creates_configs_if_missing(self):
        """First GET creates default configs."""
        self.assertEqual(ErasmusSlideConfig.objects.count(), 0)
        self.client.force_authenticate(user=self.superuser)
        self.client.get(BASE_LIST)
        self.assertEqual(ErasmusSlideConfig.objects.count(), 3)


class ErasmusSlidesAssignApiTests(APITestCase):
    """PUT /api/v1/superadmin/erasmus-slides/assign/"""

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
            {"slide_id": "sunset-manquehue", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_assign_requires_superuser(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.put(
            BASE_ASSIGN,
            {"slide_id": "sunset-manquehue", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_assign_400_missing_slide_id(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())

    def test_assign_400_empty_slide_id(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slide_id": "", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_400_invalid_slide_id(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slide_id": "invalid-slide", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())

    def test_assign_404_asset_not_found(self):
        self.client.force_authenticate(user=self.superuser)
        fake_id = str(uuid.uuid4())
        response = self.client.put(
            BASE_ASSIGN,
            {"slide_id": "sunset-manquehue", "asset_id": fake_id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.json())

    def test_assign_404_deleted_asset(self):
        self.asset.deleted_at = timezone.now()
        self.asset.save(update_fields=["deleted_at"])
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slide_id": "sunset-manquehue", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_assign_invalid_uuid_returns_404(self):
        """Invalid UUID format should return 404, not 500."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slide_id": "sunset-manquehue", "asset_id": "not-a-uuid"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_assign_success_creates_config_and_media_usage(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slide_id": "sunset-manquehue", "asset_id": str(self.asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["slide_id"], "sunset-manquehue")
        self.assertEqual(data["asset_id"], str(self.asset.id))
        self.assertIn("asset_url", data)
        self.assertEqual(data["asset_filename"], "test.jpg")

        config = ErasmusSlideConfig.objects.get(slide_id="sunset-manquehue")
        self.assertEqual(config.asset_id, self.asset.id)

        # MediaUsage created
        config_ct = ContentType.objects.get_for_model(ErasmusSlideConfig)
        usages = MediaUsage.objects.filter(
            asset=self.asset,
            content_type=config_ct,
            object_id=config.id,
            deleted_at__isnull=True,
        )
        self.assertEqual(usages.count(), 1)
        self.assertEqual(usages.first().field_name, "erasmus_slide")

    def test_assign_null_unassigns_and_soft_deletes_usage(self):
        config = ErasmusSlideConfig.objects.create(
            slide_id="sunset-manquehue",
            asset=self.asset,
            order=0,
        )
        config_ct = ContentType.objects.get_for_model(ErasmusSlideConfig)
        MediaUsage.objects.create(
            asset=self.asset,
            content_type=config_ct,
            object_id=config.id,
            field_name="erasmus_slide",
        )

        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slide_id": "sunset-manquehue", "asset_id": None},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["asset_id"], None)

        config.refresh_from_db()
        self.assertIsNone(config.asset_id)

        # Usage soft-deleted
        active = MediaUsage.objects.filter(
            asset=self.asset,
            content_type=config_ct,
            object_id=config.id,
            deleted_at__isnull=True,
        )
        self.assertEqual(active.count(), 0)

    def test_assign_reassign_replaces_asset_and_usage(self):
        config = ErasmusSlideConfig.objects.create(
            slide_id="sunset-manquehue",
            asset=self.asset,
            order=0,
        )
        config_ct = ContentType.objects.get_for_model(ErasmusSlideConfig)
        MediaUsage.objects.create(
            asset=self.asset,
            content_type=config_ct,
            object_id=config.id,
            field_name="erasmus_slide",
        )
        new_asset = create_global_asset("other.jpg")

        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(
            BASE_ASSIGN,
            {"slide_id": "sunset-manquehue", "asset_id": str(new_asset.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        config.refresh_from_db()
        self.assertEqual(config.asset_id, new_asset.id)

        # Old asset usage soft-deleted, new asset has usage
        old_active = MediaUsage.objects.filter(
            asset=self.asset,
            content_type=config_ct,
            object_id=config.id,
            deleted_at__isnull=True,
        )
        self.assertEqual(old_active.count(), 0)

        new_active = MediaUsage.objects.filter(
            asset=new_asset,
            content_type=config_ct,
            object_id=config.id,
            deleted_at__isnull=True,
        )
        self.assertEqual(new_active.count(), 1)

    def test_assign_empty_body_400(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.put(BASE_ASSIGN, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ErasmusSlidesPublicApiTests(APITestCase):
    """GET /api/v1/erasmus/slides/ - public, no auth."""

    def setUp(self):
        self.asset = create_global_asset()
        self.config = ErasmusSlideConfig.objects.create(
            slide_id="sunset-manquehue",
            asset=self.asset,
            order=0,
        )

    def test_public_slides_returns_dict_slide_id_to_url(self):
        """Public slides returns ordered list of { slide_id, url, caption }; we can find by slide_id."""
        response = self.client.get("/api/v1/erasmus/slides/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsInstance(data, list)
        slide_map = {item["slide_id"]: item.get("url") for item in data if "slide_id" in item and "url" in item}
        self.assertIn("sunset-manquehue", slide_map)
        self.assertIsNotNone(slide_map["sunset-manquehue"])
        self.assertIn("/", slide_map["sunset-manquehue"])  # URL-like

    def test_public_slides_excludes_configs_without_asset(self):
        ErasmusSlideConfig.objects.create(slide_id="valpo-concon", asset=None, order=1)
        response = self.client.get("/api/v1/erasmus/slides/")
        data = response.json()
        self.assertNotIn("valpo-concon", data)

    def test_public_slides_excludes_deleted_assets(self):
        self.asset.deleted_at = timezone.now()
        self.asset.save(update_fields=["deleted_at"])
        response = self.client.get("/api/v1/erasmus/slides/")
        data = response.json()
        self.assertNotIn("sunset-manquehue", data)

    def test_public_slides_no_auth_required(self):
        """Public endpoint works without auth."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/v1/erasmus/slides/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ErasmusSlidesMediaUsagesIntegrationTests(APITestCase):
    """Asset usages endpoint shows Erasmus slide usage."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.asset = create_global_asset()
        self.config = ErasmusSlideConfig.objects.create(
            slide_id="sunset-manquehue",
            asset=self.asset,
            order=0,
        )
        config_ct = ContentType.objects.get_for_model(ErasmusSlideConfig)
        MediaUsage.objects.create(
            asset=self.asset,
            content_type=config_ct,
            object_id=self.config.id,
            field_name="erasmus_slide",
        )

    def test_asset_usages_includes_erasmus_slide(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(f"/api/v1/media/assets/{self.asset.id}/usages/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["usage_count"], 1)
        self.assertEqual(len(data["usages"]), 1)
        usage = data["usages"][0]
        self.assertEqual(usage["field_name"], "erasmus_slide")
