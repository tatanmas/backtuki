"""
Process reservation codes from WhatsApp messages (experience or accommodation).

Extracted from MessageProcessor for manageable file size.
"""
import logging
from typing import Optional

from django.db import transaction

from apps.whatsapp.models import WhatsAppMessage, WhatsAppReservationCode, WhatsAppReservationRequest
from apps.whatsapp.services.reservation_handler import ReservationHandler
from apps.whatsapp.services.group_notification_service import GroupNotificationService
from apps.whatsapp.services.accommodation_operator_service import AccommodationOperatorService
from apps.whatsapp.services.experience_operator_service import ExperienceOperatorService
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
from apps.whatsapp.services.message_parser import MessageParser
from apps.experiences.models import Experience

logger = logging.getLogger(__name__)


class ReservationCodeProcessor:
    """Process a reservation code: create WhatsAppReservationRequest and notify operator/customer."""

    @staticmethod
    @transaction.atomic
    def process(message: WhatsAppMessage, reservation_code: str) -> Optional[WhatsAppReservationRequest]:
        """
        Process a reservation code. Returns WhatsAppReservationRequest if created/linked, None otherwise.
        """
        try:
            code_obj = WhatsAppReservationCode.objects.get(code=reservation_code)
        except WhatsAppReservationCode.DoesNotExist:
            logger.warning(
                "Reservation code %s NOT FOUND. Code must be generated via frontend before sending.",
                reservation_code,
            )
            return None

        from apps.whatsapp.services.reservation_code_generator import ReservationCodeGenerator

        if not ReservationCodeGenerator.validate_code(reservation_code):
            logger.warning("Reservation code %s is EXPIRED or status != pending.", reservation_code)
            return None

        if code_obj.linked_reservation:
            logger.info("Reservation code %s already linked to reservation %s", reservation_code, code_obj.linked_reservation.id)
            return code_obj.linked_reservation

        if code_obj.accommodation:
            return ReservationCodeProcessor._process_accommodation(message, code_obj)
        return ReservationCodeProcessor._process_experience(message, code_obj)

    @staticmethod
    def _process_accommodation(message: WhatsAppMessage, code_obj: WhatsAppReservationCode) -> Optional[WhatsAppReservationRequest]:
        """Handle accommodation reservation code."""
        accommodation = code_obj.accommodation
        group_info = AccommodationOperatorService.get_accommodation_whatsapp_group(accommodation)
        if not group_info:
            logger.warning("No WhatsApp group for accommodation %s.", accommodation.title)
            operator = None
        else:
            operator = group_info.get("operator")
            if not operator and message.chat:
                operator = message.chat.assigned_operator
            if not operator:
                binding = accommodation.operator_bindings.filter(is_active=True).first()
                operator = binding.tour_operator if binding else None

        guests = (code_obj.checkout_data or {}).get("guests", 1)
        if not operator:
            reservation = WhatsAppReservationRequest.objects.create(
                whatsapp_message=message,
                tour_code=code_obj.code,
                passengers=guests,
                operator=None,
                experience=None,
                accommodation=accommodation,
                status="received",
                timeout_at=None,
            )
            code_obj.linked_reservation = reservation
            code_obj.save()
            reservation.status = "operator_notified"
            reservation.save(update_fields=["status"])
            try:
                GroupNotificationService.send_reservation_notification(reservation)
            except Exception as e:
                logger.error("Error sending accommodation reservation to group: %s", e)
            ReservationCodeProcessor._send_waiting_to_customer(message, reservation)
            return reservation

        reservation = ReservationHandler.create_reservation(
            message=message,
            tour_code=code_obj.code,
            passengers=guests,
            operator=operator,
            experience=None,
            accommodation=accommodation,
        )
        code_obj.linked_reservation = reservation
        code_obj.save()
        ReservationHandler.mark_operator_notified(reservation)
        ReservationCodeProcessor._send_waiting_to_customer(message, reservation)
        return reservation

    @staticmethod
    def _process_experience(message: WhatsAppMessage, code_obj: WhatsAppReservationCode) -> Optional[WhatsAppReservationRequest]:
        """Handle experience reservation code."""
        experience = code_obj.experience
        if not experience and code_obj.checkout_data:
            eid = code_obj.checkout_data.get("experience_id")
            if eid:
                try:
                    experience = Experience.objects.get(id=eid)
                except Experience.DoesNotExist:
                    logger.warning("Experience %s not found for code %s", eid, code_obj.code)

        if not experience:
            logger.warning("No experience for code %s.", code_obj.code)
            return None

        logger.info("Experience found: %s (id=%s)", experience.title, experience.id)
        group_info = ExperienceOperatorService.get_experience_whatsapp_group(experience)
        if not group_info:
            logger.warning("No WhatsApp group for experience %s.", experience.title)
            operator = None
        else:
            operator = group_info.get("operator")
            if not operator and message.chat:
                operator = message.chat.assigned_operator
            if not operator:
                binding = experience.operator_bindings.filter(is_active=True).first()
                operator = binding.tour_operator if binding else None

        if not operator:
            passengers = (code_obj.checkout_data or {}).get("participants", {}).get("total", 1)
            reservation = WhatsAppReservationRequest.objects.create(
                whatsapp_message=message,
                tour_code=code_obj.code,
                passengers=passengers,
                operator=None,
                experience=experience,
                accommodation=None,
                status="received",
                timeout_at=None,
            )
            code_obj.linked_reservation = reservation
            code_obj.save()
            reservation.status = "operator_notified"
            reservation.save(update_fields=["status"])
            try:
                GroupNotificationService.send_reservation_notification(reservation)
            except Exception as e:
                logger.error("Error sending reservation to group: %s", e)
            ReservationCodeProcessor._send_waiting_to_customer(message, reservation)
            return reservation

        parsed = MessageParser.parse_message(message.content)
        passengers = parsed.get("passengers") or (code_obj.checkout_data or {}).get("participants", {}).get("total", 1)
        reservation = ReservationHandler.create_reservation(
            message=message,
            tour_code=code_obj.code,
            passengers=passengers,
            operator=operator,
            experience=experience,
            accommodation=None,
        )
        code_obj.linked_reservation = reservation
        code_obj.save()
        ReservationHandler.mark_operator_notified(reservation)
        logger.info("Notified operator for reservation %s", reservation.id)
        ReservationCodeProcessor._send_waiting_to_customer(message, reservation)
        return reservation

    @staticmethod
    def _send_waiting_to_customer(message: WhatsAppMessage, reservation: WhatsAppReservationRequest) -> None:
        """Send waiting message to customer."""
        try:
            phone = WhatsAppWebService.clean_phone_number(message.phone)
            msg = GroupNotificationService.format_waiting_message(reservation)
            WhatsAppWebService().send_message(phone, msg)
            logger.info("Sent waiting message to customer %s", phone)
        except Exception as e:
            logger.error("Error sending waiting message: %s", e)
