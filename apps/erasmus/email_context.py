"""
🚀 ENTERPRISE Email context for Erasmus activity payment confirmation.
Builds context for confirmation email (post-purchase), with post_purchase_message and placeholders.
Supports {{first_name}}, {{activity_title}}, {{instance_label}}, {{order_number}}, {{field_key}} (from registration extra_data).
"""
import re
import logging
from typing import Dict, Any, Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _format_instance_label(instance) -> str:
    """Short label for the instance (date or month/label)."""
    if getattr(instance, "scheduled_date", None):
        return instance.scheduled_date.strftime("%d/%m/%Y")
    if getattr(instance, "scheduled_label_es", None):
        return instance.scheduled_label_es
    if getattr(instance, "scheduled_month", None) and getattr(instance, "scheduled_year", None):
        return f"{instance.scheduled_month}/{instance.scheduled_year}"
    return str(getattr(instance, "id", ""))


def _replace_post_purchase_placeholders(
    message: str,
    first_name: str,
    activity_title: str,
    instance_label: str,
    order_number: str,
    extra_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Replace {{first_name}}, {{activity_title}}, {{instance_label}}, {{order_number}}, {{field_key}} in message."""
    if not message or not isinstance(message, str):
        return ""
    message = (
        message.replace("{{first_name}}", first_name or "Participante")
        .replace("{{activity_title}}", activity_title or "")
        .replace("{{instance_label}}", instance_label or "")
        .replace("{{order_number}}", order_number or "")
    )
    if extra_data and isinstance(extra_data, dict):
        for key, value in extra_data.items():
            if key and value is not None:
                message = message.replace("{{" + str(key) + "}}", str(value).strip())
    message = re.sub(r"\{\{[^}]+\}\}", lambda m: "", message)
    return message


def get_post_purchase_message_personalized(
    lead, instance, order_number: str = "", extra_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Build post-purchase message with placeholders replaced (for email or WhatsApp)."""
    first_name = (getattr(lead, "first_name", None) or "").strip() or "Participante"
    act = getattr(instance, "activity", None)
    activity_title = (getattr(act, "title_es", None) or getattr(act, "title_en", None) or "Actividad Erasmus") if act else "Actividad Erasmus"
    instance_label = _format_instance_label(instance)
    raw = _get_post_purchase_message(instance, "es")
    return _replace_post_purchase_placeholders(
        raw, first_name, activity_title, instance_label, order_number or "Pago registrado", extra_data=extra_data
    )


def _get_post_purchase_message(instance, locale: str = "es") -> str:
    """Get post-purchase message from instance (ES/EN); fallback to whatsapp message if empty."""
    msg_es = (getattr(instance, "post_purchase_message_es", None) or "").strip()
    msg_en = (getattr(instance, "post_purchase_message_en", None) or "").strip()
    if locale == "en" and msg_en:
        return msg_en
    if msg_es:
        return msg_es
    if msg_en:
        return msg_en
    # Fallback to WhatsApp message (same placeholders)
    msg_es = (getattr(instance, "whatsapp_message_es", None) or "").strip()
    msg_en = (getattr(instance, "whatsapp_message_en", None) or "").strip()
    return msg_es or msg_en or ""


def build_erasmus_activity_confirmation_context(
    order,
    link,
    image_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build context for Erasmus activity payment confirmation email.
    Pre-computes activity, instance, lead, order data and personalized post_purchase_message.
    Uses registration extra_data for {{field_key}} metatags in post_purchase_message.
    """
    try:
        from apps.erasmus.models import ErasmusActivityInstanceRegistration

        lead = link.lead
        instance = link.instance
        act = instance.activity

        first_name = (getattr(lead, "first_name", None) or "").strip() or "Participante"
        activity_title = getattr(act, "title_es", None) or getattr(act, "title_en", None) or "Actividad Erasmus"
        instance_label = _format_instance_label(instance)
        order_number = getattr(order, "order_number", "") or str(getattr(order, "id", ""))

        extra_data = None
        reg = ErasmusActivityInstanceRegistration.objects.filter(lead=lead, instance=instance).first()
        if reg and getattr(reg, "extra_data", None):
            extra_data = reg.extra_data

        post_purchase_raw = _get_post_purchase_message(instance, "es")
        post_purchase_message = _replace_post_purchase_placeholders(
            post_purchase_raw,
            first_name=first_name,
            activity_title=activity_title,
            instance_label=instance_label,
            order_number=order_number,
            extra_data=extra_data,
        )

        order_data = {
            "order_number": order_number,
            "total": float(order.total),
            "currency": getattr(order, "currency", "CLP") or "CLP",
            "created_at": order.created_at,
        }

        activity_data = {
            "title": activity_title,
            "short_description_es": getattr(act, "short_description_es", None) or "",
            "location_name": getattr(act, "location_name", None) or getattr(act, "location", None) or "",
            "location_address": getattr(act, "location_address", None) or "",
            "duration_minutes": getattr(act, "duration_minutes", None),
            "image_url": image_url,
        }

        instance_data = {
            "instance_label": instance_label,
            "scheduled_date": getattr(instance, "scheduled_date", None),
        }

        return {
            "order": order,
            "order_data": order_data,
            "activity_data": activity_data,
            "instance_data": instance_data,
            "customer_name": first_name,
            "customer_email": (getattr(lead, "email", None) or "").strip() or getattr(order, "email", ""),
            "post_purchase_message": post_purchase_message,
            "post_purchase_message_raw": post_purchase_raw,
            "activity_title": activity_title,
            "frontend_url": getattr(settings, "FRONTEND_URL", ""),
            "support_email": getattr(settings, "DEFAULT_FROM_EMAIL", ""),
            "current_year": timezone.now().year,
        }
    except Exception as e:
        logger.error(f"❌ [ERASMUS_EMAIL_CONTEXT] Error building context: {e}", exc_info=True)
        raise
