"""
Tests for Erasmus management commands: erasmus_form_preguntas, carga_subir_erasmus_leads.
"""
import json
import tempfile
from pathlib import Path

from django.test import TestCase
from django.core.management import call_command
from io import StringIO

from apps.erasmus.models import ErasmusLead, ErasmusExtraField


class ErasmusFormPreguntasCommandTests(TestCase):
    """erasmus_form_preguntas: text output and --json include fixed fields and extra fields."""

    def test_command_runs_text_output(self):
        """Running erasmus_form_preguntas prints fixed fields."""
        out = StringIO()
        call_command("erasmus_form_preguntas", stdout=out)
        self.assertIn("first_name", out.getvalue())
        self.assertIn("last_name", out.getvalue())
        self.assertIn("birth_date", out.getvalue())

    def test_command_json_output_structure(self):
        """erasmus_form_preguntas --json returns list with key, pregunta, required, type."""
        out = StringIO()
        call_command("erasmus_form_preguntas", "--json", stdout=out)
        data = json.loads(out.getvalue())
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        first = data[0]
        self.assertIn("key", first)
        self.assertIn("pregunta", first)
        self.assertIn("required", first)
        self.assertIn("type", first)

    def test_command_json_includes_extra_field_when_active(self):
        """When an ErasmusExtraField is active, --json output includes it."""
        ErasmusExtraField.objects.create(
            field_key="test_extra",
            label="Test extra",
            type="text",
            is_active=True,
            order=0,
        )
        out = StringIO()
        call_command("erasmus_form_preguntas", "--json", stdout=out)
        data = json.loads(out.getvalue())
        keys = [x["key"] for x in data]
        self.assertIn("test_extra", keys)


class CargaSubirErasmusLeadsCommandTests(TestCase):
    """carga_subir_erasmus_leads: payload with leads, --dry-run, --skip-duplicates, invalid dates."""

    def test_dry_run_valid_payload_does_not_create_leads(self):
        """--dry-run with valid leads.json does not create leads."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            leads = [
                {
                    "first_name": "Dry",
                    "last_name": "Run",
                    "birth_date": "2000-01-01",
                    "phone_country_code": "+34",
                    "phone_number": "600000001",
                    "stay_reason": "university",
                    "university": "U",
                    "degree": "D",
                    "arrival_date": "2026-02-01",
                    "departure_date": "2026-06-30",
                },
            ]
            (path / "leads.json").write_text(json.dumps(leads), encoding="utf-8")
            out = StringIO()
            call_command("carga_subir_erasmus_leads", str(path), "--dry-run", stdout=out)
            self.assertEqual(ErasmusLead.objects.count(), 0)
            self.assertIn("dry-run", out.getvalue().lower())

    def test_valid_payload_creates_lead(self):
        """Valid leads.json without --dry-run creates lead."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            leads = [
                {
                    "first_name": "Real",
                    "last_name": "Lead",
                    "birth_date": "2000-02-02",
                    "phone_country_code": "+56",
                    "phone_number": "912345678",
                    "stay_reason": "other",
                    "stay_reason_detail": "Travel",
                    "arrival_date": "2026-03-01",
                    "departure_date": "2026-07-01",
                },
            ]
            (path / "leads.json").write_text(json.dumps(leads), encoding="utf-8")
            call_command("carga_subir_erasmus_leads", str(path))
            self.assertEqual(ErasmusLead.objects.count(), 1)
            lead = ErasmusLead.objects.get(first_name="Real", last_name="Lead")
            self.assertEqual(lead.stay_reason, "other")

    def test_payload_with_leads_key(self):
        """payload.json with key 'leads' (array) is accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "payload.json").write_text(
                json.dumps({
                    "leads": [
                        {
                            "first_name": "Payload",
                            "last_name": "Key",
                            "birth_date": "2000-01-01",
                            "phone_country_code": "+34",
                            "phone_number": "600000002",
                            "stay_reason": "university",
                            "university": "U",
                            "degree": "D",
                            "arrival_date": "2026-02-01",
                            "departure_date": "2026-06-30",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            call_command("carga_subir_erasmus_leads", str(path))
            self.assertTrue(ErasmusLead.objects.filter(first_name="Payload", last_name="Key").exists())

    def test_invalid_stay_reason_raises(self):
        """Invalid stay_reason in one item causes error and no lead created."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "leads.json").write_text(
                json.dumps([
                    {
                        "first_name": "Bad",
                        "last_name": "Reason",
                        "birth_date": "2000-01-01",
                        "phone_country_code": "+34",
                        "phone_number": "600000003",
                        "stay_reason": "invalid_value",
                        "arrival_date": "2026-02-01",
                        "departure_date": "2026-06-30",
                    }
                ]),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                call_command("carga_subir_erasmus_leads", str(path))
            self.assertEqual(ErasmusLead.objects.count(), 0)

    def test_skip_duplicates_skips_existing_phone(self):
        """--skip-duplicates skips when same phone_country_code + phone_number exists."""
        ErasmusLead.objects.create(
            first_name="Existing",
            last_name="User",
            birth_date="2000-01-01",
            phone_country_code="+34",
            phone_number="600000004",
            stay_reason="university",
            arrival_date="2026-02-01",
            departure_date="2026-06-30",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "leads.json").write_text(
                json.dumps([
                    {
                        "first_name": "Duplicate",
                        "last_name": "Phone",
                        "birth_date": "2000-01-01",
                        "phone_country_code": "+34",
                        "phone_number": "600000004",
                        "stay_reason": "university",
                        "arrival_date": "2026-02-01",
                        "departure_date": "2026-06-30",
                    }
                ]),
                encoding="utf-8",
            )
            call_command("carga_subir_erasmus_leads", str(path), "--skip-duplicates")
            self.assertEqual(ErasmusLead.objects.count(), 1)
            self.assertEqual(ErasmusLead.objects.get(phone_number="600000004").first_name, "Existing")

    def test_empty_list_creates_nothing_no_error(self):
        """Empty leads array creates no leads and exits successfully."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "leads.json").write_text("[]", encoding="utf-8")
            out = StringIO()
            call_command("carga_subir_erasmus_leads", str(path), stdout=out)
            self.assertEqual(ErasmusLead.objects.count(), 0)
            self.assertIn("0 lead", out.getvalue())

    def test_batch_one_valid_one_invalid_creates_one(self):
        """One valid and one invalid item: one lead created, one error reported, exit 1."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "leads.json").write_text(
                json.dumps([
                    {
                        "first_name": "Good",
                        "last_name": "One",
                        "birth_date": "2000-01-01",
                        "phone_country_code": "+34",
                        "phone_number": "600000099",
                        "stay_reason": "university",
                        "university": "U",
                        "degree": "D",
                        "arrival_date": "2026-02-01",
                        "departure_date": "2026-06-30",
                    },
                    {
                        "first_name": "Bad",
                        "last_name": "Reason",
                        "birth_date": "2000-01-01",
                        "phone_country_code": "+34",
                        "phone_number": "600000098",
                        "stay_reason": "invalid",
                        "arrival_date": "2026-02-01",
                        "departure_date": "2026-06-30",
                    },
                ]),
                encoding="utf-8",
            )
            out = StringIO()
            err = StringIO()
            with self.assertRaises(SystemExit):
                call_command("carga_subir_erasmus_leads", str(path), stdout=out, stderr=err)
            self.assertEqual(ErasmusLead.objects.count(), 1)
            self.assertTrue(ErasmusLead.objects.filter(first_name="Good", last_name="One").exists())
            self.assertIn("Ítem 2", err.getvalue())

    def test_missing_birth_date_uses_default(self):
        """Lead without birth_date gets DEFAULT_BIRTH_DATE when importing."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "leads.json").write_text(
                json.dumps([
                    {
                        "first_name": "NoBirth",
                        "last_name": "User",
                        "phone_country_code": "+34",
                        "phone_number": "600000097",
                        "stay_reason": "other",
                        "arrival_date": "2026-02-01",
                        "departure_date": "2026-06-30",
                    }
                ]),
                encoding="utf-8",
            )
            call_command("carga_subir_erasmus_leads", str(path))
            lead = ErasmusLead.objects.get(first_name="NoBirth", last_name="User")
            self.assertEqual(str(lead.birth_date), "2000-01-01")

    def test_consent_false_accepted(self):
        """Leads with consent false are accepted (WhatsApp/manual load)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "leads.json").write_text(
                json.dumps([
                    {
                        "first_name": "Consent",
                        "last_name": "False",
                        "birth_date": "2000-01-01",
                        "phone_country_code": "+34",
                        "phone_number": "600000096",
                        "stay_reason": "other",
                        "arrival_date": "2026-02-01",
                        "departure_date": "2026-06-30",
                        "accept_tc_erasmus": False,
                        "accept_privacy_erasmus": False,
                    }
                ]),
                encoding="utf-8",
            )
            call_command("carga_subir_erasmus_leads", str(path))
            lead = ErasmusLead.objects.get(first_name="Consent", last_name="False")
            self.assertFalse(lead.accept_tc_erasmus)
            self.assertFalse(lead.accept_privacy_erasmus)
