"""
Orchestrates processing of incoming WhatsApp messages.

Delegates to:
- MessageSaver: save message and chat
- ReservationCodeProcessor: process reservation codes (experience/accommodation)
- OperatorResponseProcessor: process operator 1/2 responses
- customer_confirmation_processor: customer SI for free reservations, code error message
"""
import logging
from typing import Dict

from django.utils import timezone

from apps.whatsapp.models import WhatsAppMessage
from apps.whatsapp.services.message_saver import MessageSaver
from apps.whatsapp.services.message_parser import MessageParser
from apps.whatsapp.services.reservation_code_processor import ReservationCodeProcessor
from apps.whatsapp.services.operator_response_processor import OperatorResponseProcessor
from apps.whatsapp.services.customer_confirmation_processor import (
    send_code_error_message,
    process_customer_confirmation,
)

logger = logging.getLogger(__name__)


class MessageProcessor:
    """Entry point for processing incoming WhatsApp messages."""

    @staticmethod
    def parse_timestamp(raw_timestamp) -> timezone.datetime:
        """Parse timestamp from Node.js (seconds or milliseconds). Returns timezone-aware datetime."""
        if isinstance(raw_timestamp, (int, float)) and raw_timestamp > 0:
            try:
                if raw_timestamp > 10000000000:
                    return timezone.datetime.fromtimestamp(raw_timestamp / 1000, tz=timezone.utc)
                return timezone.datetime.fromtimestamp(raw_timestamp, tz=timezone.utc)
            except (ValueError, OSError) as e:
                logger.warning("Error parsing timestamp %s: %s", raw_timestamp, e)
        return timezone.now()

    @staticmethod
    def get_or_create_chat(*args, **kwargs):
        """Delegate to MessageSaver (backward compatibility)."""
        return MessageSaver.get_or_create_chat(*args, **kwargs)

    @staticmethod
    def save_message(*args, **kwargs):
        """Delegate to MessageSaver (backward compatibility)."""
        return MessageSaver.save_message(*args, **kwargs)

    @staticmethod
    def process_reservation_code(message: WhatsAppMessage, reservation_code: str):
        """Delegate to ReservationCodeProcessor."""
        return ReservationCodeProcessor.process(message, reservation_code)

    @staticmethod
    def process_incoming_message(data: Dict) -> Dict:
        """
        Process an incoming WhatsApp message: save, then handle reservation code / operator response / customer SI.
        """
        whatsapp_id = data.get("id")
        if not whatsapp_id:
            return {"status": "error", "message": "Missing message ID"}

        existing_message = WhatsAppMessage.objects.filter(whatsapp_id=whatsapp_id).first()
        if existing_message and existing_message.processed:
            return {"status": "already_processed", "message_id": str(existing_message.id)}

        from_me = data.get("from_me", False)
        message_timestamp = MessageProcessor.parse_timestamp(data.get("timestamp"))

        message, is_new = MessageSaver.save_message(
            whatsapp_id=whatsapp_id,
            phone=data.get("phone", ""),
            text=data.get("text", ""),
            chat_id=data.get("chat_id"),
            chat_type=data.get("chat_type", "individual"),
            timestamp=message_timestamp,
            from_me=from_me,
            chat_name=data.get("chat_name"),
            whatsapp_name=data.get("whatsapp_name"),
            profile_picture_url=data.get("profile_picture_url"),
            sender_name=data.get("sender_name"),
            sender_phone=data.get("sender_phone"),
            media_type=data.get("media_type") or None,
            reply_to_whatsapp_id=data.get("reply_to_whatsapp_id") or None,
        )

        if not message:
            return {"status": "error", "message": "Failed to save message"}

        if from_me:
            return {"status": "saved", "message_id": str(message.id), "type": "outgoing"}

        message.processed = True
        message.save(update_fields=["processed"])

        parsed = MessageParser.parse_message(message.content)
        reservation_code = parsed.get("reservation_code")
        logger.info(
            "Message content_len=%s parsed_reservation_code=%s content_preview=%s",
            len(message.content or ""),
            reservation_code,
            repr((message.content or "")[:100]),
        )

        if reservation_code:
            try:
                logger.info("Processing reservation code: %s", reservation_code)
                reservation = ReservationCodeProcessor.process(message, reservation_code)
                if reservation:
                    return {
                        "status": "reservation_created",
                        "message_id": str(message.id),
                        "reservation_id": str(reservation.id),
                    }
                send_code_error_message(message, reservation_code)
            except Exception as e:
                logger.exception("Error processing reservation code %s: %s", reservation_code, e)
                send_code_error_message(message, reservation_code)

        text = (data.get("text") or "").strip().lower()
        sender_phone = data.get("sender_phone", "")
        if text in ["1", "2", "sí", "si", "yes", "no", "confirmar", "rechazar"] and sender_phone:
            operator_result = OperatorResponseProcessor.process(
                {"text": text, "phone": sender_phone, "chat_id": data.get("chat_id")}
            )
            if operator_result.get("status") in ["availability_confirmed", "rejected"]:
                return {
                    "status": "operator_response_processed",
                    "message_id": str(message.id),
                    "reservation_status": operator_result.get("status"),
                }

        if text in ["sí", "si", "yes", "confirmar"]:
            customer_result = process_customer_confirmation(message, data)
            if customer_result:
                return customer_result

        return {"status": "processed", "message_id": str(message.id)}

    # Backward compatibility: external code may call _process_operator_response
    @staticmethod
    def _process_operator_response(data: Dict) -> Dict:
        return OperatorResponseProcessor.process(data)

    @staticmethod
    def _send_code_error_message(message: WhatsAppMessage, reservation_code: str) -> None:
        send_code_error_message(message, reservation_code)

    @staticmethod
    def _process_customer_confirmation(message, data: Dict):
        return process_customer_confirmation(message, data)
