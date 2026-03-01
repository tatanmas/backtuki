"""
Minimal API tests: options, register (without flow_id), source from query and body.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.erasmus.models import ErasmusLead


class ErasmusOptionsApiTests(TestCase):
    """GET options/ returns destinations, interests, extra_fields."""

    def setUp(self):
        self.client = APIClient()

    def test_options_returns_200_and_structure(self):
        """GET erasmus/options/ is public and returns countries, destinations, interests, extra_fields."""
        response = self.client.get(reverse("erasmus-options"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("countries", data)
        self.assertIn("destinations", data)
        self.assertIn("interests", data)
        self.assertIn("extra_fields", data)
        self.assertIn("destinations_list", data)
        self.assertIn("destination_slugs_with_guides", data)


class ErasmusRegisterApiTests(TestCase):
    """POST register/ creates lead; source from query or body; no flow_id is ok."""

    def setUp(self):
        self.client = APIClient()

    def test_register_minimal_creates_lead(self):
        """POST register/ with minimal required fields creates ErasmusLead."""
        payload = {
            "first_name": "Min",
            "last_name": "User",
            "birth_date": "2000-05-10",
            "phone_country_code": "+34",
            "phone_number": "600111222",
            "stay_reason": "university",
            "university": "U Min",
            "degree": "CS",
            "arrival_date": "2026-02-01",
            "departure_date": "2026-06-30",
            "accept_tc_erasmus": True,
            "accept_privacy_erasmus": True,
            "opt_in_community": False,
        }
        response = self.client.post(reverse("erasmus-register"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ErasmusLead.objects.filter(first_name="Min", last_name="User").exists())

    def test_register_with_source_slug_in_body(self):
        """POST register/ with source_slug in body stores it on the lead."""
        payload = {
            "first_name": "Source",
            "last_name": "Body",
            "birth_date": "2000-01-01",
            "phone_country_code": "+34",
            "phone_number": "612345678",
            "stay_reason": "university",
            "university": "U Test",
            "degree": "D",
            "arrival_date": "2026-03-01",
            "departure_date": "2026-08-01",
            "accept_tc_erasmus": True,
            "accept_privacy_erasmus": True,
            "opt_in_community": False,
            "source_slug": "whatsapp_campaign",
        }
        response = self.client.post(reverse("erasmus-register"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        lead = ErasmusLead.objects.get(first_name="Source", last_name="Body")
        self.assertEqual(lead.source_slug, "whatsapp_campaign")
