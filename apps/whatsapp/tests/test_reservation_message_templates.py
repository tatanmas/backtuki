"""
Tests for WhatsApp reservation message template resolution and rendering.

Covers: experience override -> global -> operator -> default;
accommodation -> hotel/rental_hub -> global -> operator -> default.
"""
from django.test import TestCase

from apps.whatsapp.services.templates.renderer import (
    _get_template_from_entity_templates,
    _get_template_for_reservation,
    TemplateRenderer,
)
from apps.whatsapp.services.templates.defaults import DEFAULT_TEMPLATES
from apps.whatsapp.models import (
    WhatsAppReservationMessageConfig,
    TourOperator,
    OperatorMessageTemplate,
    WhatsAppMessage,
    WhatsAppReservationRequest,
)
from apps.experiences.models import Experience
from apps.accommodations.models import Accommodation, Hotel, RentalHub
from apps.organizers.models import Organizer
from core.testing.factories import create_whatsapp_message, create_tour_operator, create_whatsapp_chat


class GetTemplateFromEntityTests(TestCase):
    """Test _get_template_from_entity_templates helper."""

    def test_returns_none_for_none_entity(self):
        self.assertIsNone(_get_template_from_entity_templates(None, "reservation_request"))

    def test_returns_none_when_entity_has_no_whatsapp_message_templates(self):
        class Entity:
            pass
        self.assertIsNone(_get_template_from_entity_templates(Entity(), "reservation_request"))

    def test_returns_none_when_templates_not_dict(self):
        class Entity:
            whatsapp_message_templates = "not-a-dict"
        self.assertIsNone(_get_template_from_entity_templates(Entity(), "reservation_request"))

    def test_returns_none_when_key_missing(self):
        class Entity:
            whatsapp_message_templates = {}
        self.assertIsNone(_get_template_from_entity_templates(Entity(), "reservation_request"))

    def test_returns_none_when_value_empty(self):
        class Entity:
            whatsapp_message_templates = {"reservation_request": "   "}
        self.assertIsNone(_get_template_from_entity_templates(Entity(), "reservation_request"))

    def test_returns_stripped_value_when_set(self):
        class Entity:
            whatsapp_message_templates = {"reservation_request": "  Custom text  "}
        result = _get_template_from_entity_templates(Entity(), "reservation_request")
        self.assertEqual(result, "Custom text")


class GetTemplateForReservationTests(TestCase):
    """Test _get_template_for_reservation resolution order."""

    def setUp(self):
        self.organizer = Organizer.objects.create(name="Org", slug="org-slug")
        self.msg = create_whatsapp_message()
        self.operator = create_tour_operator(name="Op")
        self.experience = Experience.objects.create(
            title="Tour Test",
            slug="tour-test",
            organizer=self.organizer,
            status="published",
        )
        self.reservation_with_experience = WhatsAppReservationRequest.objects.create(
            whatsapp_message=self.msg,
            experience=self.experience,
            operator=self.operator,
            tour_code="RES-001",
            status="operator_notified",
        )

    def test_experience_override_used_when_set(self):
        self.experience.whatsapp_message_templates = {
            "customer_waiting": "Custom waiting {{nombre_cliente}}",
        }
        self.experience.save()
        result = _get_template_for_reservation(self.reservation_with_experience, "customer_waiting")
        self.assertEqual(result, "Custom waiting {{nombre_cliente}}")

    def test_global_config_used_when_no_experience_override(self):
        WhatsAppReservationMessageConfig.objects.get_or_create(
            config_key=WhatsAppReservationMessageConfig.CONFIG_KEY,
            defaults={"templates": {}},
        )
        config = WhatsAppReservationMessageConfig.objects.get(
            config_key=WhatsAppReservationMessageConfig.CONFIG_KEY
        )
        config.templates = {"customer_waiting": "Global waiting {{codigo}}"}
        config.save()
        result = _get_template_for_reservation(self.reservation_with_experience, "customer_waiting")
        self.assertEqual(result, "Global waiting {{codigo}}")

    def test_operator_template_used_when_no_experience_or_global(self):
        OperatorMessageTemplate.objects.create(
            operator=self.operator,
            message_type="customer_waiting",
            template="Operator template {{experiencia}}",
            is_active=True,
        )
        result = _get_template_for_reservation(self.reservation_with_experience, "customer_waiting")
        self.assertEqual(result, "Operator template {{experiencia}}")

    def test_default_used_when_nothing_else_set(self):
        result = _get_template_for_reservation(
            self.reservation_with_experience, "customer_waiting"
        )
        self.assertIn("Estimado/a", result)
        self.assertEqual(result, DEFAULT_TEMPLATES["customer_waiting"])

    def test_reservation_without_operator_uses_default(self):
        res = WhatsAppReservationRequest.objects.create(
            whatsapp_message=self.msg,
            experience=self.experience,
            operator=None,
            tour_code="RES-002",
            status="operator_notified",
        )
        result = _get_template_for_reservation(res, "reservation_request")
        self.assertEqual(result, DEFAULT_TEMPLATES["reservation_request"])


class GetTemplateForReservationAccommodationTests(TestCase):
    """Test 3-layer resolution for accommodation reservations."""

    def setUp(self):
        self.organizer = Organizer.objects.create(name="Org", slug="org-acc")
        self.msg = create_whatsapp_message()
        self.operator = create_tour_operator(name="Op")
        self.hub = RentalHub.objects.create(
            name="Central Test",
            slug="central-test",
        )
        self.hotel = Hotel.objects.create(
            name="Hotel Test",
            slug="hotel-test",
        )
        self.accommodation = Accommodation.objects.create(
            title="Room A",
            slug="room-a",
            organizer=self.organizer,
            status="published",
            rental_hub=self.hub,
            hotel=self.hotel,
        )
        self.reservation = WhatsAppReservationRequest.objects.create(
            whatsapp_message=self.msg,
            accommodation=self.accommodation,
            operator=self.operator,
            tour_code="RES-ACC",
            status="operator_notified",
        )

    def test_accommodation_override_used_first(self):
        self.accommodation.whatsapp_message_templates = {
            "customer_waiting": "Room override",
        }
        self.accommodation.save()
        result = _get_template_for_reservation(self.reservation, "customer_waiting")
        self.assertEqual(result, "Room override")

    def test_hotel_override_used_when_no_accommodation_override(self):
        self.hotel.whatsapp_message_templates = {
            "customer_waiting": "Hotel override",
        }
        self.hotel.save()
        result = _get_template_for_reservation(self.reservation, "customer_waiting")
        self.assertEqual(result, "Hotel override")

    def test_rental_hub_override_used_when_no_accommodation_override(self):
        self.accommodation.hotel = None
        self.accommodation.save()
        self.hub.whatsapp_message_templates = {
            "customer_waiting": "Hub override",
        }
        self.hub.save()
        result = _get_template_for_reservation(self.reservation, "customer_waiting")
        self.assertEqual(result, "Hub override")

    def test_global_then_default_when_no_entity_overrides(self):
        result = _get_template_for_reservation(self.reservation, "customer_waiting")
        self.assertEqual(result, DEFAULT_TEMPLATES["customer_waiting"])


class TemplateRendererRenderTests(TestCase):
    """Test TemplateRenderer.render and render_message."""

    def test_render_replaces_variables(self):
        template = "Hola {{nombre_cliente}}, codigo {{codigo}}."
        context = {"nombre_cliente": "Juan", "codigo": "RES-123"}
        result = TemplateRenderer.render(template, context)
        self.assertEqual(result, "Hola Juan, codigo RES-123.")

    def test_render_strips_unreplaced_variables(self):
        template = "Hola {{nombre_cliente}} {{unknown}}."
        context = {"nombre_cliente": "Juan"}
        result = TemplateRenderer.render(template, context)
        self.assertIn("Juan", result)
        self.assertNotIn("{{unknown}}", result)

    def test_render_message_returns_non_empty_string(self):
        org = Organizer.objects.create(name="O", slug="o")
        exp = Experience.objects.create(
            title="E", slug="e", organizer=org, status="published"
        )
        msg = create_whatsapp_message()
        op = create_tour_operator()
        res = WhatsAppReservationRequest.objects.create(
            whatsapp_message=msg,
            experience=exp,
            operator=op,
            tour_code="X",
            status="operator_notified",
        )
        result = TemplateRenderer.render_message(
            op, "customer_waiting", res, code_obj=None
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
