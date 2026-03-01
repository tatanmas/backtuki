"""
Tests for Erasmus registration flow: track-visit creates PlatformFlow + ERASMUS_LINK_VISIT,
track-step records events, register with flow_id completes the flow.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.erasmus.models import ErasmusLead
from core.models import PlatformFlow, PlatformFlowEvent


class ErasmusFlowTrackingTests(TestCase):
    """Track-visit, track-step, and register with flow_id."""

    def setUp(self):
        self.client = APIClient()

    def test_track_visit_creates_flow_and_event(self):
        """POST track-visit/ with source creates erasmus_registration flow and ERASMUS_LINK_VISIT event."""
        response = self.client.post(
            reverse("erasmus-track-visit"),
            {"source": "test_link", "utm_medium": "whatsapp"},
            format="json",
        )
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        data = response.json()
        self.assertIn("flow_id", data)
        flow_id = data["flow_id"]
        self.assertIsNotNone(flow_id)

        flow = PlatformFlow.objects.get(id=flow_id)
        self.assertEqual(flow.flow_type, "erasmus_registration")
        self.assertEqual(flow.status, "in_progress")
        self.assertEqual(flow.metadata.get("source_slug"), "test_link")
        self.assertEqual(flow.metadata.get("utm_medium"), "whatsapp")

        events = list(flow.events.values_list("step", flat=True))
        self.assertIn("ERASMUS_LINK_VISIT", events)

    def test_track_step_records_event(self):
        """POST track-step/ with flow_id and step records ERASMUS_FORM_STARTED or ERASMUS_STEP_COMPLETED."""
        response = self.client.post(
            reverse("erasmus-track-visit"),
            {"source": "step_test"},
            format="json",
        )
        flow_id = response.json().get("flow_id")
        self.assertIsNotNone(flow_id)

        step_response = self.client.post(
            reverse("erasmus-track-step"),
            {"flow_id": flow_id, "step": "ERASMUS_FORM_STARTED", "step_number": 1},
            format="json",
        )
        self.assertEqual(step_response.status_code, status.HTTP_200_OK)

        flow = PlatformFlow.objects.get(id=flow_id)
        steps = list(flow.events.values_list("step", flat=True))
        self.assertIn("ERASMUS_LINK_VISIT", steps)
        self.assertIn("ERASMUS_FORM_STARTED", steps)

    def test_track_step_requires_flow_id_and_step(self):
        """POST track-step/ without flow_id or step returns 400."""
        r1 = self.client.post(
            reverse("erasmus-track-step"),
            {"step": "ERASMUS_FORM_STARTED"},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_400_BAD_REQUEST)
        r2 = self.client.post(
            reverse("erasmus-track-step"),
            {"flow_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_track_step_flow_not_found_404(self):
        """POST track-step/ with non-existent flow_id returns 404."""
        response = self.client.post(
            reverse("erasmus-track-step"),
            {"flow_id": "00000000-0000-0000-0000-000000000000", "step": "ERASMUS_FORM_STARTED"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_register_with_flow_id_completes_flow(self):
        """POST register/ with flow_id in body creates lead and completes PlatformFlow with ERASMUS_FORM_SUBMITTED."""
        visit_response = self.client.post(
            reverse("erasmus-track-visit"),
            {"source": "submit_test"},
            format="json",
        )
        flow_id = visit_response.json().get("flow_id")
        self.assertIsNotNone(flow_id)

        payload = {
            "first_name": "Flow",
            "last_name": "User",
            "birth_date": "2000-01-15",
            "phone_country_code": "+34",
            "phone_number": "612345678",
            "stay_reason": "university",
            "university": "U Test",
            "degree": "Ing",
            "arrival_date": "2026-03-01",
            "departure_date": "2026-07-01",
            "accept_tc_erasmus": True,
            "accept_privacy_erasmus": True,
            "opt_in_community": False,
            "flow_id": flow_id,
        }
        reg_response = self.client.post(reverse("erasmus-register"), payload, format="json")
        self.assertEqual(reg_response.status_code, status.HTTP_201_CREATED)

        lead = ErasmusLead.objects.get(first_name="Flow", last_name="User")
        self.assertIsNotNone(lead.id)

        flow = PlatformFlow.objects.get(id=flow_id)
        self.assertEqual(flow.status, "completed")
        self.assertIsNotNone(flow.completed_at)
        self.assertEqual(flow.metadata.get("erasmus_lead_id"), str(lead.id))

        steps = list(flow.events.values_list("step", flat=True))
        self.assertIn("ERASMUS_FORM_SUBMITTED", steps)

    def test_track_step_already_completed_returns_400(self):
        """POST track-step/ for a flow that is already completed returns 400."""
        visit_response = self.client.post(
            reverse("erasmus-track-visit"),
            {"source": "completed_test"},
            format="json",
        )
        flow_id = visit_response.json().get("flow_id")
        payload = {
            "first_name": "Complete",
            "last_name": "Flow",
            "birth_date": "2000-01-01",
            "phone_country_code": "+34",
            "phone_number": "699999999",
            "stay_reason": "university",
            "university": "U",
            "degree": "D",
            "arrival_date": "2026-03-01",
            "departure_date": "2026-07-01",
            "accept_tc_erasmus": True,
            "accept_privacy_erasmus": True,
            "opt_in_community": False,
            "flow_id": flow_id,
        }
        self.client.post(reverse("erasmus-register"), payload, format="json")
        step_response = self.client.post(
            reverse("erasmus-track-step"),
            {"flow_id": flow_id, "step": "ERASMUS_STEP_COMPLETED", "step_number": 2},
            format="json",
        )
        self.assertEqual(step_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already completed", step_response.json().get("detail", "").lower())
