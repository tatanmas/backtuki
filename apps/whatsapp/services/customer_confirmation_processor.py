"""
Customer confirmation (SI for free reservation) and code error message.

Extracted from MessageProcessor for single responsibility.
"""
import logging
from typing import Dict, Optional

from apps.whatsapp.models import WhatsAppMessage, WhatsAppReservationRequest
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
from apps.whatsapp.services.reservation_handler import ReservationHandler

logger = logging.getLogger(__name__)


def send_code_error_message(message: WhatsAppMessage, reservation_code: str) -> None:
    """Send a helpful message when reservation code processing fails."""
    try:
        phone = WhatsAppWebService.clean_phone_number(message.phone)
        if not phone:
            logger.warning("Cannot send code error message: no phone number")
            return
        msg = (
            f"Hola. Recibimos su mensaje con el código {reservation_code}, pero no pudimos procesarlo. "
            "Puede que el código haya expirado o no exista. Por favor, genere un nuevo código desde la página "
            "y envíe el mensaje nuevamente."
        )
        WhatsAppWebService().send_message(phone, msg)
        logger.info("Sent code error message to %s for code %s", phone, reservation_code)
    except Exception as e:
        logger.error("Failed to send code error message: %s", e)


def process_customer_confirmation(message: WhatsAppMessage, data: Dict) -> Optional[Dict]:
    """
    Process customer "SI" for free reservation. Returns result dict if processed, None otherwise.
    """
    customer_phone_raw = data.get("phone", "") or (message.phone if message else "")
    if not customer_phone_raw:
        return None
    customer_phone = WhatsAppWebService.clean_phone_number(customer_phone_raw)
    if not customer_phone:
        return None

    reservations = WhatsAppReservationRequest.objects.filter(
        status="availability_confirmed",
    ).select_related("whatsapp_message").order_by("-created_at")

    for reservation in reservations:
        msg_phone = WhatsAppWebService.clean_phone_number(reservation.whatsapp_message.phone)
        if msg_phone == customer_phone:
            total = ReservationHandler._get_total_from_checkout(reservation)
            if total <= 0:
                ReservationHandler.confirm_reservation(reservation)
                logger.info("Customer confirmed free reservation %s", reservation.id)
                return {
                    "status": "customer_confirmed",
                    "message_id": str(message.id),
                    "reservation_id": str(reservation.id),
                }
            break
    return None
