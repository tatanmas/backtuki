"""
Tests for public car rental API: list, detail, availability filtering.
"""
from datetime import date
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status

from apps.car_rental.models import CarRentalCompany, Car, CarBlockedDate, CarReservation

BASE = "/api/v1/car-rental/public"


class PublicCarListTests(APITestCase):
    """GET /api/v1/car-rental/public/"""

    def setUp(self):
        self.company = CarRentalCompany.objects.create(
            name="Test Rent",
            slug="test-rent",
        )
        Car.objects.create(
            company=self.company,
            title="Published Car",
            slug="published-car",
            status="published",
            price_per_day=Decimal("30000"),
            currency="CLP",
        )
        Car.objects.create(
            company=self.company,
            title="Draft Car",
            slug="draft-car",
            status="draft",
            price_per_day=Decimal("25000"),
            currency="CLP",
        )

    def test_list_returns_only_published(self):
        response = self.client.get(BASE + "/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Published Car")

    def test_list_unauthenticated_ok(self):
        response = self.client.get(BASE + "/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PublicCarDetailTests(APITestCase):
    """GET /api/v1/car-rental/public/<slug_or_id>/"""

    def setUp(self):
        self.company = CarRentalCompany.objects.create(
            name="Detail Rent",
            slug="detail-rent",
        )
        self.car = Car.objects.create(
            company=self.company,
            title="Test Car",
            slug="test-car",
            status="published",
            price_per_day=Decimal("35000"),
            currency="CLP",
        )

    def test_detail_by_slug_success(self):
        response = self.client.get(BASE + "/test-car/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Test Car")
        self.assertIn("price_per_day", response.data)
        self.assertIn("company_name", response.data)

    def test_detail_by_id_success(self):
        response = self.client.get(BASE + f"/{self.car.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.car.id))

    def test_detail_404_draft(self):
        Car.objects.create(
            company=self.company,
            title="Draft Only",
            slug="draft-only",
            status="draft",
            price_per_day=Decimal("20000"),
            currency="CLP",
        )
        response = self.client.get(BASE + "/draft-only/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_404_invalid_slug(self):
        response = self.client.get(BASE + "/nonexistent-slug-xyz/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PublicCarListAvailabilityTests(APITestCase):
    """List with pickup_date/return_date excludes blocked and reserved cars."""

    def setUp(self):
        self.company = CarRentalCompany.objects.create(name="A", slug="a")
        self.car1 = Car.objects.create(
            company=self.company,
            title="Car Available",
            slug="car-available",
            status="published",
        )
        self.car2 = Car.objects.create(
            company=self.company,
            title="Car Blocked",
            slug="car-blocked",
            status="published",
        )
        self.car3 = Car.objects.create(
            company=self.company,
            title="Car Reserved",
            slug="car-reserved",
            status="published",
        )

    def test_list_without_dates_returns_all_published(self):
        response = self.client.get(BASE + "/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_list_with_dates_excludes_blocked(self):
        CarBlockedDate.objects.create(car=self.car2, date=date(2025, 5, 10))
        response = self.client.get(
            BASE + "/",
            {"pickup_date": "2025-05-08", "return_date": "2025-05-12"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [c["slug"] for c in response.data]
        self.assertIn("car-available", slugs)
        self.assertNotIn("car-blocked", slugs)

    def test_list_with_dates_excludes_reserved(self):
        CarReservation.objects.create(
            reservation_id="RES-001",
            car=self.car3,
            status="paid",
            pickup_date=date(2025, 5, 9),
            return_date=date(2025, 5, 11),
            first_name="X",
            last_name="Y",
            email="x@y.com",
            total=Decimal("100000"),
            currency="CLP",
        )
        response = self.client.get(
            BASE + "/",
            {"pickup_date": "2025-05-08", "return_date": "2025-05-12"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = [c["slug"] for c in response.data]
        self.assertNotIn("car-reserved", slugs)
