"""
Tests for Superadmin Accommodations API: GET detail (full response), PATCH (all fields + edge cases),
POST create (validation, slug, organizer, 201 shape).

Enterprise: robust testing, all edge cases, nothing slips through.
"""
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from django.utils import timezone

from apps.accommodations.models import Accommodation
from apps.organizers.models import Organizer

User = get_user_model()

BASE = "/api/v1/superadmin/accommodations"


class SuperAdminAccommodationListEdgeTests(APITestCase):
    """GET list: search and organizer_id filter (complement existing list tests)."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.org1 = Organizer.objects.create(name="Org One", slug="org-one")
        self.org2 = Organizer.objects.create(name="Org Two", slug="org-two")
        self.acc1 = Accommodation.objects.create(
            title="Cabaña Norte",
            slug="cabana-norte",
            organizer=self.org1,
            status="published",
            city="Santiago",
            country="Chile",
            guests=2,
            price=Decimal("50000"),
            currency="CLP",
        )
        self.acc2 = Accommodation.objects.create(
            title="Cabaña Sur",
            slug="cabana-sur",
            organizer=self.org2,
            status="published",
            city="Valdivia",
            country="Chile",
            guests=4,
            price=Decimal("80000"),
            currency="CLP",
        )

    def test_list_filter_by_organizer_id(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + f"/?organizer_id={self.org1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["organizer_id"], str(self.org1.id))
        self.assertEqual(response.data["results"][0]["title"], "Cabaña Norte")

    def test_list_search_by_title(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + "/?search=Norte")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertIn("Norte", response.data["results"][0]["title"])

    def test_list_search_by_city(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + "/?search=Valdivia")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["city"], "Valdivia")

    def test_list_excludes_deleted(self):
        self.acc1.deleted_at = timezone.now()
        self.acc1.save(update_fields=["deleted_at"])
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + "/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.acc2.id))


class SuperAdminAccommodationDetailFullTests(APITestCase):
    """GET /api/v1/superadmin/accommodations/<uuid>/ — full response shape and edge cases."""

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
            property_type="cabin",
            description="Long desc",
            short_description="Short",
            location_name="Valle",
            location_address="Calle 123",
            latitude=Decimal("-30.5"),
            longitude=Decimal("-70.2"),
            city="Cochiguaz",
            country="Chile",
            guests=4,
            bedrooms=2,
            full_bathrooms=2,
            half_bathrooms=0,
            beds=3,
            price=Decimal("90000"),
            currency="CLP",
            amenities=["WiFi", "Cocina"],
            not_amenities=["TV"],
        )

    def test_detail_requires_superuser(self):
        response = self.client.get(BASE + f"/{self.acc.id}/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_detail_forbidden_for_normal_user(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(BASE + f"/{self.acc.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detail_404_invalid_uuid(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + "/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)

    def test_detail_404_deleted_accommodation(self):
        self.acc.deleted_at = timezone.now()
        self.acc.save(update_fields=["deleted_at"])
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + f"/{self.acc.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_200_full_response_keys(self):
        """GET detail returns all keys needed for the editor (including gallery, room_categories)."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(BASE + f"/{self.acc.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data["title"], "Test Cabin")
        self.assertEqual(data["slug"], "test-cabin")
        self.assertEqual(data["description"], "Long desc")
        self.assertEqual(data["short_description"], "Short")
        self.assertEqual(data["status"], "published")
        self.assertEqual(data["property_type"], "cabin")
        self.assertEqual(data["organizer_id"], str(self.organizer.id))
        self.assertEqual(data["organizer_name"], "Test Org")
        self.assertEqual(data["location_name"], "Valle")
        self.assertEqual(data["location_address"], "Calle 123")
        self.assertAlmostEqual(float(data["latitude"]), -30.5)
        self.assertAlmostEqual(float(data["longitude"]), -70.2)
        self.assertEqual(data["city"], "Cochiguaz")
        self.assertEqual(data["country"], "Chile")
        self.assertEqual(data["guests"], 4)
        self.assertEqual(data["bedrooms"], 2)
        self.assertEqual(data["full_bathrooms"], 2)
        self.assertEqual(data["half_bathrooms"], 0)
        self.assertEqual(data["bathrooms"], 2)
        self.assertEqual(data["beds"], 3)
        self.assertAlmostEqual(float(data["price"]), 90000.0)
        self.assertEqual(data["currency"], "CLP")
        self.assertEqual(data["amenities"], ["WiFi", "Cocina"])
        self.assertEqual(data["not_amenities"], ["TV"])
        self.assertIn("photo_count", data)
        self.assertIn("gallery_items", data)
        self.assertIsInstance(data["gallery_items"], list)
        self.assertIn("room_categories", data)
        self.assertIsInstance(data["room_categories"], list)
        self.assertGreater(len(data["room_categories"]), 0)


class SuperAdminAccommodationPatchTests(APITestCase):
    """PATCH /api/v1/superadmin/accommodations/<uuid>/ — all fields and edge cases."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            email="super@test.com",
            password="superpass123",
        )
        self.organizer = Organizer.objects.create(name="Test Org", slug="test-org")
        self.acc = Accommodation.objects.create(
            title="Original",
            slug="original-slug",
            organizer=self.organizer,
            status="draft",
            property_type="cabin",
            city="Santiago",
            country="Chile",
            guests=2,
            price=Decimal("50000"),
            currency="CLP",
        )

    def test_patch_requires_superuser(self):
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={"title": "Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_404_invalid_uuid(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + "/00000000-0000-0000-0000-000000000000/",
            data={"title": "X"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_404_deleted(self):
        self.acc.deleted_at = timezone.now()
        self.acc.save(update_fields=["deleted_at"])
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(BASE + f"/{self.acc.id}/", data={"title": "X"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_partial_title_only(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={"title": "New Title"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "New Title")
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.title, "New Title")
        self.assertEqual(self.acc.slug, "original-slug")
        self.assertEqual(self.acc.city, "Santiago")

    def test_patch_slug_not_updatable(self):
        """PATCH does not accept slug; slug remains unchanged."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={"slug": "hacked-slug"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.slug, "original-slug")

    def test_patch_status_valid_values(self):
        for st in ("draft", "published", "cancelled"):
            self.client.force_authenticate(user=self.superuser)
            response = self.client.patch(
                BASE + f"/{self.acc.id}/",
                data={"status": st},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=f"status={st}")
            self.assertEqual(response.data["status"], st)
            self.acc.refresh_from_db()
            self.assertEqual(self.acc.status, st)

    def test_patch_status_invalid_ignored(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={"status": "invalid_status"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.status, "draft")

    def test_patch_property_type_valid(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={"property_type": "house"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["property_type"], "house")
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.property_type, "house")

    def test_patch_property_type_invalid_ignored(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={"property_type": "invalid_type"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.property_type, "cabin")

    def test_patch_location_and_capacity(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={
                "location_name": "Valle de Elqui",
                "location_address": "Calle 456",
                "latitude": -29.9,
                "longitude": -70.25,
                "city": "Vicuña",
                "country": "Chile",
                "guests": 6,
                "bedrooms": 3,
                "bathrooms": 2,
                "beds": 4,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.location_name, "Valle de Elqui")
        self.assertEqual(self.acc.guests, 6)
        self.assertEqual(self.acc.bedrooms, 3)
        self.assertEqual(self.acc.full_bathrooms, 2)
        self.assertEqual(self.acc.half_bathrooms, 0)
        self.assertEqual(self.acc.beds, 4)
        self.assertAlmostEqual(float(self.acc.latitude), -29.9)
        self.assertAlmostEqual(float(self.acc.longitude), -70.25)

    def test_patch_guests_below_one_clamped_to_one(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={"guests": 0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.guests, 1)

    def test_patch_negative_price_clamped_to_zero(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={"price": -100},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.price, Decimal("0"))

    def test_patch_lat_lng_null(self):
        self.acc.latitude = Decimal("-30.0")
        self.acc.longitude = Decimal("-70.0")
        self.acc.save(update_fields=["latitude", "longitude"])
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={"latitude": None, "longitude": None},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.acc.refresh_from_db()
        self.assertIsNone(self.acc.latitude)
        self.assertIsNone(self.acc.longitude)

    def test_patch_amenities_and_not_amenities(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            BASE + f"/{self.acc.id}/",
            data={
                "amenities": ["WiFi", "Parrilla"],
                "not_amenities": ["TV", "A/C"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.amenities, ["WiFi", "Parrilla"])
        self.assertEqual(self.acc.not_amenities, ["TV", "A/C"])

    def test_patch_empty_body_returns_200_unchanged(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(BASE + f"/{self.acc.id}/", data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Original")


class SuperAdminAccommodationCreateTests(APITestCase):
    """POST /api/v1/superadmin/accommodations/ — create with all validations and edge cases."""

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

    def test_create_requires_superuser(self):
        response = self.client.post(
            BASE + "/",
            data={"organizer_id": str(self.organizer.id), "title": "New Cabin"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_forbidden_for_normal_user(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.post(
            BASE + "/",
            data={"organizer_id": str(self.organizer.id), "title": "New Cabin"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_400_missing_title(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            BASE + "/",
            data={"organizer_id": str(self.organizer.id), "title": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("title", str(response.data).lower() or response.data.get("detail", ""))

    def test_create_400_title_whitespace_only(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            BASE + "/",
            data={"organizer_id": str(self.organizer.id), "title": "   "},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_400_missing_organizer_id(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            BASE + "/",
            data={"title": "New Cabin"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("organizer", str(response.data).lower() or response.data.get("detail", ""))

    def test_create_400_organizer_not_found(self):
        self.client.force_authenticate(user=self.superuser)
        fake_id = str(uuid.uuid4())
        response = self.client.post(
            BASE + "/",
            data={"organizer_id": fake_id, "title": "New Cabin"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("organizador", str(response.data).lower() or response.data.get("detail", "").lower())

    def test_create_400_duplicate_slug(self):
        Accommodation.objects.create(
            title="Existing",
            slug="my-cabin",
            organizer=self.organizer,
            status="draft",
            guests=2,
            price=Decimal("0"),
            currency="CLP",
        )
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            BASE + "/",
            data={
                "organizer_id": str(self.organizer.id),
                "title": "Other",
                "slug": "my-cabin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("slug", str(response.data).lower() or response.data.get("detail", "").lower())

    def test_create_201_minimal_payload(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            BASE + "/",
            data={
                "organizer_id": str(self.organizer.id),
                "title": "Minimal Cabin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data
        self.assertEqual(data["title"], "Minimal Cabin")
        self.assertIn("slug", data)
        self.assertTrue(len(data["slug"]) > 0)
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["property_type"], "cabin")
        self.assertEqual(data["organizer_id"], str(self.organizer.id))
        self.assertEqual(data["country"], "Chile")
        self.assertEqual(data["guests"], 2)
        self.assertEqual(data["bedrooms"], 1)
        self.assertEqual(data["bathrooms"], 1)
        self.assertEqual(data["beds"], 1)
        self.assertIn("id", data)
        self.assertIn("gallery_items", data)
        self.assertIn("room_categories", data)
        self.assertIn("photo_count", data)
        self.assertIn("amenities", data)
        self.assertIn("not_amenities", data)
        # Slug derived from title
        self.assertTrue("minimal" in data["slug"].lower() or "cabin" in data["slug"].lower())
        acc = Accommodation.objects.get(id=data["id"])
        self.assertEqual(acc.title, "Minimal Cabin")
        self.assertEqual(acc.organizer_id, self.organizer.id)

    def test_create_201_with_slug(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            BASE + "/",
            data={
                "organizer_id": str(self.organizer.id),
                "title": "Custom Title",
                "slug": "custom-slug-here",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["slug"], "custom-slug-here")
        acc = Accommodation.objects.get(id=response.data["id"])
        self.assertEqual(acc.slug, "custom-slug-here")

    def test_create_201_full_optional_fields(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            BASE + "/",
            data={
                "organizer_id": str(self.organizer.id),
                "title": "Full Cabin",
                "slug": "full-cabin",
                "description": "Long description",
                "short_description": "Short",
                "status": "published",
                "property_type": "villa",
                "location_name": "Valle",
                "location_address": "Calle 1",
                "latitude": -30.0,
                "longitude": -70.0,
                "city": "La Serena",
                "country": "Chile",
                "guests": 8,
                "bedrooms": 4,
                "bathrooms": 3,
                "beds": 5,
                "price": 150000,
                "currency": "CLP",
                "amenities": ["WiFi", "Piscina"],
                "not_amenities": ["TV"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        acc = Accommodation.objects.get(id=response.data["id"])
        self.assertEqual(acc.title, "Full Cabin")
        self.assertEqual(acc.slug, "full-cabin")
        self.assertEqual(acc.description, "Long description")
        self.assertEqual(acc.short_description, "Short")
        self.assertEqual(acc.status, "published")
        self.assertEqual(acc.property_type, "villa")
        self.assertEqual(acc.location_name, "Valle")
        self.assertEqual(acc.guests, 8)
        self.assertEqual(acc.bedrooms, 4)
        self.assertEqual(acc.full_bathrooms, 3)
        self.assertEqual(acc.half_bathrooms, 0)
        self.assertEqual(acc.beds, 5)
        self.assertEqual(acc.price, Decimal("150000"))
        self.assertEqual(acc.amenities, ["WiFi", "Piscina"])
        self.assertEqual(acc.not_amenities, ["TV"])
        self.assertAlmostEqual(float(acc.latitude), -30.0)
        self.assertAlmostEqual(float(acc.longitude), -70.0)
