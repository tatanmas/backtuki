"""
Payment processor tests: accommodation order creation, webhook branch, serializers.
"""
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient

from apps.events.models import Order
from apps.accommodations.models import AccommodationReservation
from apps.whatsapp.models import WhatsAppReservationCode, WhatsAppReservationRequest
from payment_processor.models import Payment, PaymentProvider, PaymentMethod
from payment_processor.serializers import PaymentSerializer
from core.testing import (
    create_accommodation,
    create_whatsapp_message,
    create_reservation_code_for_accommodation,
    create_whatsapp_reservation_request,
    create_accommodation_reservation,
    create_order_accommodation,
)


class AccommodationOrderCreationTests(TestCase):
    """Order with order_kind=accommodation and accommodation_reservation."""

    def setUp(self):
        self.acc = create_accommodation()
        self.acc_res = create_accommodation_reservation(self.acc, total=Decimal("200000"))

    def test_create_order_accommodation_factory(self):
        """Order from factory has order_kind=accommodation, accommodation_reservation set, status pending."""
        order = create_order_accommodation(self.acc_res)
        self.assertEqual(order.order_kind, "accommodation")
        self.assertEqual(order.accommodation_reservation_id, self.acc_res.id)
        self.assertIsNone(order.experience_reservation_id)
        self.assertIsNone(order.event_id)
        self.assertEqual(order.total, self.acc_res.total)
        self.assertEqual(order.status, "pending")

    def test_create_order_accommodation_api_success(self):
        """POST create-order-accommodation with valid codigo → 201, order_id/order_number, Order linked to reservation."""
        code_obj = create_reservation_code_for_accommodation(self.acc)
        msg = create_whatsapp_message()
        reservation = create_whatsapp_reservation_request(
            msg, accommodation=self.acc, tour_code=code_obj.code, status="availability_confirmed"
        )
        acc_res = create_accommodation_reservation(self.acc)
        reservation.linked_accommodation_reservation = acc_res
        reservation.save(update_fields=["linked_accommodation_reservation"])
        code_obj.linked_reservation = reservation
        code_obj.save(update_fields=["linked_reservation"])

        client = APIClient()
        response = client.post(
            "/api/v1/whatsapp/create-order-accommodation/",
            {"codigo": code_obj.code},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("order_id", data)
        self.assertIn("order_number", data)
        self.assertEqual(Decimal(str(data["total"])), acc_res.total)

        order = Order.objects.get(id=data["order_id"])
        self.assertEqual(order.order_kind, "accommodation")
        self.assertEqual(order.accommodation_reservation_id, acc_res.id)

    def test_create_order_accommodation_api_idempotent(self):
        code_obj = create_reservation_code_for_accommodation(self.acc)
        msg = create_whatsapp_message()
        reservation = create_whatsapp_reservation_request(
            msg, accommodation=self.acc, tour_code=code_obj.code, status="availability_confirmed"
        )
        reservation.linked_accommodation_reservation = self.acc_res
        reservation.save(update_fields=["linked_accommodation_reservation"])
        code_obj.linked_reservation = reservation
        code_obj.save(update_fields=["linked_reservation"])

        existing_order = create_order_accommodation(self.acc_res)

        client = APIClient()
        response = client.post(
            "/api/v1/whatsapp/create-order-accommodation/",
            {"codigo": code_obj.code},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["order_id"], str(existing_order.id))


class AccommodationOrderCreationEdgeTests(TestCase):
    """Create-order-accommodation API: missing codigo, code not found, expired, not linked, not ready, already paid."""

    def setUp(self):
        self.acc = create_accommodation()
        self.acc_res = create_accommodation_reservation(self.acc)
        self.client = APIClient()
        self.url = "/api/v1/whatsapp/create-order-accommodation/"

    def test_create_order_missing_codigo_400(self):
        """Missing or empty codigo → 400 with error message."""
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("codigo", response.json().get("error", "").lower())

    def test_create_order_code_not_found_404(self):
        """Nonexistent code → 404."""
        response = self.client.post(
            self.url,
            {"codigo": "RES-NONEXISTENT-00000000-XXXX"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_create_order_expired_code_410(self):
        """Expired code → 410 with expirado message."""
        from datetime import timedelta
        code_obj = create_reservation_code_for_accommodation(
            self.acc,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        response = self.client.post(
            self.url,
            {"codigo": code_obj.code},
            format="json",
        )
        self.assertEqual(response.status_code, 410)
        self.assertIn("expirado", response.json().get("error", "").lower())

    def test_create_order_not_linked_409(self):
        """Code without linked_reservation → 409 (solicitud no vinculada)."""
        code_obj = create_reservation_code_for_accommodation(self.acc)
        self.assertIsNone(code_obj.linked_reservation_id)
        response = self.client.post(
            self.url,
            {"codigo": code_obj.code},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("vinculada", response.json().get("error", "").lower())

    def test_create_order_reservation_not_ready_409(self):
        """Request status operator_notified (not ready for payment) → 409 with status in body."""
        code_obj = create_reservation_code_for_accommodation(self.acc)
        msg = create_whatsapp_message()
        reservation = create_whatsapp_reservation_request(
            msg,
            accommodation=self.acc,
            tour_code=code_obj.code,
            status="operator_notified",
        )
        reservation.linked_accommodation_reservation = self.acc_res
        reservation.save(update_fields=["linked_accommodation_reservation"])
        code_obj.linked_reservation = reservation
        code_obj.save(update_fields=["linked_reservation"])

        response = self.client.post(
            self.url,
            {"codigo": code_obj.code},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "operator_notified")

    def test_create_order_acc_res_already_paid_409(self):
        """AccommodationReservation already paid → 409 (reserva ya no pendiente)."""
        self.acc_res.status = "paid"
        self.acc_res.save(update_fields=["status"])
        code_obj = create_reservation_code_for_accommodation(self.acc)
        msg = create_whatsapp_message()
        reservation = create_whatsapp_reservation_request(
            msg,
            accommodation=self.acc,
            tour_code=code_obj.code,
            status="availability_confirmed",
        )
        reservation.linked_accommodation_reservation = self.acc_res
        reservation.save(update_fields=["linked_accommodation_reservation"])
        code_obj.linked_reservation = reservation
        code_obj.save(update_fields=["linked_reservation"])

        response = self.client.post(
            self.url,
            {"codigo": code_obj.code},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("pendiente", response.json().get("error", "").lower())


class AccommodationWebhookSuccessTests(TestCase):
    """When payment confirms successfully, accommodation reservation is marked paid and WhatsApp request updated."""

    def setUp(self):
        self.acc = create_accommodation()
        self.acc_res = create_accommodation_reservation(self.acc)
        self.order = create_order_accommodation(self.acc_res)
        self.msg = create_whatsapp_message()
        self.wa_req = create_whatsapp_reservation_request(
            self.msg,
            accommodation=self.acc,
            status="availability_confirmed",
            linked_accommodation_reservation=self.acc_res,
        )
        provider = PaymentProvider.objects.create(
            name="TestProvider",
            provider_type="transbank_webpay_plus",
            is_active=True,
        )
        method = PaymentMethod.objects.create(
            provider=provider,
            method_type="credit_card",
            display_name="Test Card",
            is_active=True,
        )
        self.payment = Payment.objects.create(
            order=self.order,
            amount=self.order.total,
            payment_method=method,
            status="pending",
            buy_order=f"ACC-{self.acc_res.reservation_id}",
            token="test_token_123",
        )

    @patch("apps.whatsapp.services.payment_success_notifier.WhatsAppWebService")
    def test_accommodation_reservation_marked_paid_and_wa_updated(self, mock_ws_class):
        """finalize_accommodation_payment → AccommodationReservation status=paid, paid_at set; WhatsAppRequest payment_received_at set. WhatsApp send mocked to avoid CI errors."""
        from payment_processor.services import finalize_accommodation_payment

        mock_ws_class.return_value.send_message = MagicMock()

        finalize_accommodation_payment(self.payment)

        self.acc_res.refresh_from_db()
        self.assertEqual(self.acc_res.status, "paid")
        self.assertIsNotNone(self.acc_res.paid_at)
        self.wa_req.refresh_from_db()
        self.assertIsNotNone(self.wa_req.payment_received_at)


class PaymentSerializerAccommodationTests(TestCase):
    """PaymentSerializer get_event_info includes accommodation data for accommodation orders."""

    def setUp(self):
        self.acc = create_accommodation(title="Cabaña Test", slug="cabana-test")
        self.acc_res = create_accommodation_reservation(self.acc)
        self.order = create_order_accommodation(self.acc_res)
        provider = PaymentProvider.objects.create(
            name="P",
            provider_type="transbank_webpay_plus",
            is_active=True,
        )
        method = PaymentMethod.objects.create(
            provider=provider,
            method_type="credit_card",
            display_name="M",
            is_active=True,
        )
        self.payment = Payment.objects.create(
            order=self.order,
            amount=self.order.total,
            payment_method=method,
            status="pending",
            buy_order="BO-123",
        )

    def test_serializer_event_info_accommodation(self):
        """PaymentSerializer.event_info for accommodation order includes title, id, ticket_holders (Alojamiento)."""
        serializer = PaymentSerializer(self.payment)
        data = serializer.data
        event_info = data.get("event_info")
        self.assertIsNotNone(event_info)
        self.assertEqual(event_info["title"], self.acc.title)
        self.assertEqual(event_info["id"], str(self.acc.id))
        self.assertIn("ticket_holders", event_info)
        self.assertEqual(len(event_info["ticket_holders"]), 1)
        self.assertEqual(event_info["ticket_holders"][0]["tier_name"], "Alojamiento")
