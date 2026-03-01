"""
Process operator responses (1=confirm, 2=reject) from group or by phone.

Supports both experience and accommodation reservations.
"""
import logging
from typing import Dict

from apps.whatsapp.models import (
    WhatsAppChat,
    WhatsAppReservationRequest,
    TourOperator,
    ExperienceGroupBinding,
    AccommodationGroupBinding,
    CarGroupBinding,
)
from apps.whatsapp.services.reservation_handler import ReservationHandler

logger = logging.getLogger(__name__)


class OperatorResponseProcessor:
    """Process operator confirm/reject (1/2, sí/no)."""

    @staticmethod
    def process(data: Dict) -> Dict:
        """
        Find pending reservation by group or operator phone, then confirm or reject.
        Returns dict with status: availability_confirmed | rejected | no_pending_reservation.
        """
        text = (data.get("text") or "").strip().lower()
        is_confirm = text in ["1", "sí", "si", "yes", "confirmar"]
        phone = data.get("phone", "")
        chat_id = data.get("chat_id", "")

        reservation = None
        operator = None

        if chat_id and "@g.us" in str(chat_id):
            group_chat = WhatsAppChat.objects.filter(chat_id=chat_id, type="group").first()
            if group_chat:
                # Experience group bindings
                exp_ids = list(
                    ExperienceGroupBinding.objects.filter(
                        whatsapp_group=group_chat,
                        is_active=True,
                    ).values_list("experience_id", flat=True)
                )
                if exp_ids:
                    reservation = WhatsAppReservationRequest.objects.filter(
                        experience_id__in=exp_ids,
                        status="operator_notified",
                    ).order_by("-created_at").first()
                # Accommodation group bindings (if no experience reservation)
                if not reservation:
                    acc_ids = list(
                        AccommodationGroupBinding.objects.filter(
                            whatsapp_group=group_chat,
                            is_active=True,
                        ).values_list("accommodation_id", flat=True)
                    )
                    if acc_ids:
                        reservation = WhatsAppReservationRequest.objects.filter(
                            accommodation_id__in=acc_ids,
                            status="operator_notified",
                        ).order_by("-created_at").first()
                # Car (car_rental) group bindings (if no experience/accommodation reservation)
                if not reservation:
                    car_ids = list(
                        CarGroupBinding.objects.filter(
                            whatsapp_group=group_chat,
                            is_active=True,
                        ).values_list("car_id", flat=True)
                    )
                    if car_ids:
                        reservation = WhatsAppReservationRequest.objects.filter(
                            car_id__in=car_ids,
                            status="operator_notified",
                        ).order_by("-created_at").first()
                if reservation:
                    operator = reservation.operator

        if not reservation and phone:
            operator = (
                TourOperator.objects.filter(whatsapp_number=phone).first()
                or TourOperator.objects.filter(contact_phone=phone).first()
            )
            if operator:
                reservation = WhatsAppReservationRequest.objects.filter(
                    operator=operator,
                    status="operator_notified",
                ).order_by("-created_at").first()

        if not reservation:
            logger.info("No pending reservation for chat_id=%s phone=%s", chat_id, phone)
            return {"status": "no_pending_reservation"}

        op_name = operator.name if operator else "grupo"
        if is_confirm:
            ReservationHandler.confirm_availability(reservation)
            logger.info("Reservation %s availability confirmed by %s", reservation.id, op_name)
            return {
                "status": "availability_confirmed",
                "confirmed": True,
                "reservation_id": str(reservation.id),
            }
        ReservationHandler.reject_reservation(reservation)
        logger.info("Reservation %s rejected by %s", reservation.id, op_name)
        return {
            "status": "rejected",
            "confirmed": False,
            "reservation_id": str(reservation.id),
        }
