"""
Save WhatsApp messages and chats with idempotency.

Extracted from MessageProcessor for manageable file size and single responsibility.
"""
import logging
from typing import Optional, Tuple

from django.db import transaction
from django.db.utils import IntegrityError
from django.utils import timezone

from apps.whatsapp.models import WhatsAppMessage, WhatsAppChat

logger = logging.getLogger(__name__)


class MessageSaver:
    """Handles saving messages and get-or-create chat."""

    @staticmethod
    @transaction.atomic
    def get_or_create_chat(
        chat_id: str,
        chat_type: str,
        chat_name: Optional[str] = None,
        whatsapp_name: Optional[str] = None,
        profile_picture_url: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Tuple[WhatsAppChat, bool]:
        """Get or create a WhatsApp chat. Returns (chat, created)."""
        if not chat_id:
            raise ValueError("chat_id is required")

        display_name = chat_name
        if not display_name or display_name == "Unknown":
            if chat_type == "individual" and phone:
                phone_clean = phone.replace("@c.us", "").replace("@g.us", "").replace("@lid", "")
                if phone_clean and phone_clean.isdigit():
                    if phone_clean.startswith("56") and len(phone_clean) == 11:
                        display_name = f"+{phone_clean[:2]} {phone_clean[2:3]} {phone_clean[3:7]} {phone_clean[7:]}"
                    else:
                        display_name = f"+{phone_clean}"
                else:
                    display_name = phone_clean or chat_id.replace("@c.us", "").replace("@g.us", "")
            else:
                display_name = chat_id.replace("@c.us", "").replace("@g.us", "")

        defaults = {
            "name": display_name,
            "type": chat_type,
            "is_active": True,
            "whatsapp_name": whatsapp_name or "",
            "profile_picture_url": profile_picture_url or "",
        }
        chat, created = WhatsAppChat.objects.get_or_create(chat_id=chat_id, defaults=defaults)

        if not created:
            update_fields = []
            if display_name and display_name != chat.name and display_name != "Unknown":
                if (
                    chat.name == "Unknown"
                    or "Unknown" in chat.name
                    or len(display_name) > len(chat.name)
                    or (display_name.startswith("+") and not chat.name.startswith("+"))
                ):
                    chat.name = display_name
                    update_fields.append("name")
            if whatsapp_name and whatsapp_name != chat.whatsapp_name:
                chat.whatsapp_name = whatsapp_name
                update_fields.append("whatsapp_name")
            if profile_picture_url and profile_picture_url != chat.profile_picture_url:
                chat.profile_picture_url = profile_picture_url
                update_fields.append("profile_picture_url")
            if chat.type != chat_type:
                chat.type = chat_type
                update_fields.append("type")
            if update_fields:
                chat.save(update_fields=update_fields)

        return chat, created

    @staticmethod
    @transaction.atomic
    def save_message(
        whatsapp_id: str,
        phone: str,
        text: str,
        chat_id: str,
        chat_type: str,
        timestamp: timezone.datetime,
        from_me: bool = False,
        chat_name: Optional[str] = None,
        whatsapp_name: Optional[str] = None,
        profile_picture_url: Optional[str] = None,
        sender_name: Optional[str] = None,
        sender_phone: Optional[str] = None,
        media_type: Optional[str] = None,
        reply_to_whatsapp_id: Optional[str] = None,
    ) -> Tuple[Optional[WhatsAppMessage], bool]:
        """Save a WhatsApp message with idempotency. Returns (message, is_new)."""
        existing_message = WhatsAppMessage.objects.filter(whatsapp_id=whatsapp_id).first()
        if existing_message:
            logger.debug("Message %s already exists", whatsapp_id)
            return existing_message, False

        chat, _ = MessageSaver.get_or_create_chat(
            chat_id=chat_id,
            chat_type=chat_type,
            chat_name=chat_name,
            whatsapp_name=whatsapp_name,
            profile_picture_url=profile_picture_url,
            phone=phone,
        )

        message_metadata = {}
        if chat_type == "group":
            if sender_name:
                message_metadata["sender_name"] = sender_name
            if sender_phone:
                message_metadata["sender_phone"] = sender_phone

        message_type = "out" if from_me else "in"
        create_kwargs = {
            "whatsapp_id": whatsapp_id,
            "phone": phone,
            "type": message_type,
            "content": text,
            "timestamp": timestamp,
            "chat": chat,
            "is_automated": False,
            "metadata": message_metadata or {},
        }
        if media_type:
            create_kwargs["media_type"] = media_type
        if reply_to_whatsapp_id:
            create_kwargs["reply_to_whatsapp_id"] = reply_to_whatsapp_id
        try:
            message = WhatsAppMessage.objects.create(**create_kwargs)
        except IntegrityError:
            # Race: another request created the same whatsapp_id (e.g. duplicate webhook delivery).
            existing_message = WhatsAppMessage.objects.filter(whatsapp_id=whatsapp_id).first()
            if existing_message:
                logger.debug("Message %s already exists (race)", whatsapp_id)
                return existing_message, False
            raise

        update_fields = []
        if not chat.last_message_at or timestamp > chat.last_message_at:
            chat.last_message_at = timestamp
            update_fields.append("last_message_at")
        preview = (text or "")[:255]
        if preview and preview != (chat.last_message_preview or ""):
            chat.last_message_preview = preview
            update_fields.append("last_message_preview")
        if update_fields:
            chat.save(update_fields=update_fields)

        logger.info("Saved message %s (type=%s, from_me=%s)", message.id, message_type, from_me)
        return message, True
