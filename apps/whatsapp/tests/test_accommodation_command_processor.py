from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.accommodations.models import (
    AccommodationBlockedDate,
    AccommodationReservation,
    Hotel,
)
from apps.whatsapp.models import AccommodationGroupBinding
from apps.whatsapp.services.accommodation_command_processor import (
    AccommodationCommandProcessor,
)
from apps.whatsapp.services.group_notification_service import GroupNotificationService
from core.testing import (
    create_accommodation,
    create_accommodation_operator_binding,
    create_accommodation_reservation,
    create_organizer,
    create_tour_operator,
    create_whatsapp_chat,
    create_whatsapp_message,
    create_whatsapp_reservation_request,
)


class AccommodationCommandProcessorTests(TestCase):
    def setUp(self):
        self.organizer = create_organizer(name="Stay Org", slug="stay-org")
        self.group = create_whatsapp_chat(
            chat_id="120363555000@g.us",
            name="Hotel Ops",
            type="group",
        )
        self.operator = create_tour_operator(
            name="Hotel Operator",
            default_whatsapp_group=self.group,
        )
        self.operator.whatsapp_number = "56911112222"
        self.operator.save(update_fields=["whatsapp_number"])

        self.accommodation = create_accommodation(
            organizer=self.organizer,
            title="Suite Vista Mar",
            slug="suite-vista-mar",
            unit_number="305",
            external_id="PB-305",
        )
        create_accommodation_operator_binding(self.accommodation, self.operator)

    @patch("apps.whatsapp.services.accommodation_command_processor.WhatsAppWebService")
    def test_list_command_returns_accessible_properties(self, mock_ws_class):
        hotel = Hotel.objects.create(
            slug="hotel-playa",
            name="Hotel Playa",
            default_whatsapp_group=self.group,
        )
        room = create_accommodation(
            organizer=self.organizer,
            title="Habitacion 204",
            slug="habitacion-204",
            hotel=hotel,
        )
        direct = create_accommodation(
            organizer=self.organizer,
            title="Depto 12B",
            slug="depto-12b",
        )
        AccommodationGroupBinding.objects.create(
            accommodation=direct,
            whatsapp_group=self.group,
            is_active=True,
        )

        mock_ws_class.return_value.send_message = MagicMock()

        handled = AccommodationCommandProcessor.process_and_reply(
            "Tuki propiedades",
            self.group.chat_id,
            sender_phone="56911112222",
        )

        self.assertTrue(handled)
        sent_message = mock_ws_class.return_value.send_message.call_args.args[1]
        self.assertIn("Habitacion 204", sent_message)
        self.assertIn("Depto 12B", sent_message)
        self.assertIn("Suite Vista Mar", sent_message)
        self.assertIn("#1", sent_message)
        self.assertIn("Tuki bloquear 5", sent_message)
        self.assertEqual(room.hotel_id, hotel.id)

    @patch("apps.whatsapp.services.accommodation_command_processor.WhatsAppWebService")
    def test_block_range_by_index_creates_blocked_dates(self, mock_ws_class):
        mock_ws_class.return_value.send_message = MagicMock()

        handled = AccommodationCommandProcessor.process_and_reply(
            "Tuki bloquear 1 2026-03-20 a 2026-03-22",
            self.group.chat_id,
            sender_phone="56911112222",
        )

        self.assertTrue(handled)
        dates = list(
            AccommodationBlockedDate.objects.filter(accommodation=self.accommodation)
            .order_by("date")
            .values_list("date", flat=True)
        )
        self.assertEqual(
            dates,
            [date(2026, 3, 20), date(2026, 3, 21), date(2026, 3, 22)],
        )
        sent_message = mock_ws_class.return_value.send_message.call_args.args[1]
        self.assertIn("3 fecha(s) bloqueadas", sent_message)

    @patch("apps.whatsapp.services.accommodation_command_processor.WhatsAppWebService")
    def test_availability_command_marks_reserved_days(self, mock_ws_class):
        create_accommodation_reservation(
            self.accommodation,
            check_in=date(2026, 4, 10),
            check_out=date(2026, 4, 12),
            status="paid",
        )
        mock_ws_class.return_value.send_message = MagicMock()

        handled = AccommodationCommandProcessor.process_and_reply(
            "Tuki disponibilidad suite-vista-mar 2026-04-10 a 2026-04-12",
            self.group.chat_id,
            sender_phone="56911112222",
        )

        self.assertTrue(handled)
        sent_message = mock_ws_class.return_value.send_message.call_args.args[1]
        self.assertIn("2026-04-10: reservado", sent_message)
        self.assertIn("2026-04-11: reservado", sent_message)
        self.assertIn("2026-04-12: libre", sent_message)

    @patch("apps.whatsapp.services.accommodation_command_processor.WhatsAppWebService")
    def test_reservations_command_lists_future_reservations(self, mock_ws_class):
        reservation = create_accommodation_reservation(
            self.accommodation,
            check_in=date(2026, 5, 1),
            check_out=date(2026, 5, 4),
            first_name="Ana",
            last_name="Perez",
            status="pending",
        )
        mock_ws_class.return_value.send_message = MagicMock()

        handled = AccommodationCommandProcessor.process_and_reply(
            "Tuki reservas PB-305",
            self.group.chat_id,
            sender_phone="56911112222",
        )

        self.assertTrue(handled)
        sent_message = mock_ws_class.return_value.send_message.call_args.args[1]
        self.assertIn(reservation.reservation_id, sent_message)
        self.assertIn("Ana Perez", sent_message)
        self.assertIn("2026-05-01 -> 2026-05-04", sent_message)

    @patch("apps.whatsapp.services.accommodation_command_processor.WhatsAppWebService")
    def test_sender_phone_must_match_configured_operator(self, mock_ws_class):
        mock_ws_class.return_value.send_message = MagicMock()

        handled = AccommodationCommandProcessor.process_and_reply(
            "Tuki bloquear 1 2026-03-20",
            self.group.chat_id,
            sender_phone="56999990000",
        )

        self.assertTrue(handled)
        self.assertEqual(
            AccommodationBlockedDate.objects.filter(accommodation=self.accommodation).count(),
            0,
        )
        sent_message = mock_ws_class.return_value.send_message.call_args.args[1]
        self.assertIn("No puedo ejecutar ese comando", sent_message)


class AccommodationGroupNotificationTests(TestCase):
    @patch("apps.whatsapp.services.group_notification_service.WhatsAppWebService")
    @patch("apps.whatsapp.services.group_notification_service.GroupNotificationService.format_reservation_notification")
    def test_send_reservation_notification_uses_accommodation_group(
        self,
        mock_format,
        mock_ws_class,
    ):
        group = create_whatsapp_chat(chat_id="120363777000@g.us", name="Central Ops", type="group")
        operator = create_tour_operator(name="Central Operator", default_whatsapp_group=group)
        accommodation = create_accommodation(title="Depto Central", slug="depto-central")
        create_accommodation_operator_binding(accommodation, operator)
        message = create_whatsapp_message(chat=group)
        reservation = create_whatsapp_reservation_request(
            message,
            accommodation=accommodation,
            status="operator_notified",
        )
        mock_format.return_value = "Nueva reserva alojamiento"
        mock_ws_class.return_value.send_message = MagicMock()

        result = GroupNotificationService.send_reservation_notification(reservation)

        self.assertTrue(result)
        mock_ws_class.return_value.send_message.assert_called_once_with(
            "",
            "Nueva reserva alojamiento",
            group_id=group.chat_id,
        )
        self.assertEqual(AccommodationReservation.objects.count(), 0)
