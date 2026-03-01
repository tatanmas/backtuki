"""
Tests for car_rental models: CarRentalCompany, Car, CarBlockedDate, CarReservation.
"""
from datetime import date
from decimal import Decimal
from django.test import TestCase

from apps.car_rental.models import CarRentalCompany, Car, CarBlockedDate, CarReservation


class CarRentalCompanyModelTests(TestCase):
    """Test CarRentalCompany creation and fields."""

    def test_company_creation(self):
        company = CarRentalCompany.objects.create(
            name="Rent Chile",
            slug="rent-chile",
            short_description="Alquiler de autos",
            is_active=True,
        )
        self.assertEqual(company.name, "Rent Chile")
        self.assertEqual(company.slug, "rent-chile")
        self.assertEqual(company.conditions, {})
        self.assertTrue(company.is_active)

    def test_company_with_conditions(self):
        company = CarRentalCompany.objects.create(
            name="Auto Sur",
            slug="auto-sur",
            conditions={"min_age": 21, "deposit": "100000"},
        )
        self.assertEqual(company.conditions.get("min_age"), 21)


class CarModelTests(TestCase):
    """Test Car creation and relation to company."""

    def setUp(self):
        self.company = CarRentalCompany.objects.create(
            name="Test Rent",
            slug="test-rent",
        )

    def test_car_creation(self):
        car = Car.objects.create(
            company=self.company,
            title="Sedan Económico",
            slug="sedan-economico",
            status="published",
            price_per_day=Decimal("25000"),
            currency="CLP",
        )
        self.assertEqual(car.company, self.company)
        self.assertEqual(car.title, "Sedan Económico")
        self.assertEqual(car.status, "published")
        self.assertTrue(car.inherit_company_conditions)
        self.assertEqual(car.included, [])
        self.assertEqual(car.not_included, [])

    def test_car_slug_unique(self):
        Car.objects.create(
            company=self.company,
            title="Auto A",
            slug="auto-a",
            status="draft",
        )
        car2 = Car(
            company=self.company,
            title="Auto B",
            slug="auto-a",
            status="draft",
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            car2.save()


class CarBlockedDateModelTests(TestCase):
    """Test CarBlockedDate and unique_together (car, date)."""

    def setUp(self):
        self.company = CarRentalCompany.objects.create(name="C", slug="c")
        self.car = Car.objects.create(
            company=self.company,
            title="Car",
            slug="car-one",
            status="published",
        )

    def test_blocked_date_creation(self):
        bd = CarBlockedDate.objects.create(car=self.car, date=date(2025, 3, 15))
        self.assertEqual(bd.car, self.car)
        self.assertEqual(bd.date, date(2025, 3, 15))
        self.assertEqual(self.car.blocked_dates.count(), 1)


class CarReservationModelTests(TestCase):
    """Test CarReservation creation and relation to Car."""

    def setUp(self):
        self.company = CarRentalCompany.objects.create(name="R", slug="r")
        self.car = Car.objects.create(
            company=self.company,
            title="SUV",
            slug="suv",
            status="published",
        )

    def test_reservation_creation(self):
        res = CarReservation.objects.create(
            reservation_id="CAR-TEST-001",
            car=self.car,
            status="pending",
            pickup_date=date(2025, 4, 1),
            return_date=date(2025, 4, 3),
            pickup_time="10:00",
            return_time="10:00",
            first_name="Juan",
            last_name="Pérez",
            email="juan@example.com",
            total=Decimal("75000"),
            currency="CLP",
        )
        self.assertEqual(res.car, self.car)
        self.assertEqual(res.reservation_id, "CAR-TEST-001")
        self.assertEqual(res.status, "pending")
        self.assertEqual(res.pickup_time, "10:00")
