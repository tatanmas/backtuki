"""
Notify external partners (e.g. Rumi) via WhatsApp when certain Erasmus events occur.
Housing: when a new lead has wants_rumi4students_contact=True, send housing-relevant details to the configured group.
Activity inscription: when a lead expresses interest in an activity instance, notify configured groups (new person + total inscribed).
"""
import logging
from .models import (
    ErasmusLead,
    ErasmusPartnerNotificationConfig,
    ErasmusActivityNotificationConfig,
    ErasmusActivityInstance,
)

logger = logging.getLogger(__name__)

RUMI_HOUSING_SLUG = "rumi_housing"

# Keys from lead.extra_data that are relevant for housing (Rumi).
HOUSING_EXTRA_KEYS = (
    "accommodation_help_where",
    "accommodation_help_budget_monthly",
    "accommodation_help_types",
)


def _format_date(d) -> str:
    """Format a date for the message (readable)."""
    if d is None:
        return "—"
    if hasattr(d, "strftime"):
        return d.strftime("%d/%m/%Y")
    return str(d)


def _format_rumi_housing_message(lead: ErasmusLead) -> str:
    """Build the WhatsApp message with only housing-relevant fields (no destinations, interests)."""
    lines = [
        "🆕 *Nuevo registro Erasmus – Housing (Rumi)*",
        "",
        f"*Nombre:* {lead.first_name or ''} {lead.last_name or ''}".strip(),
        f"*Email:* {lead.email or '—'}",
        f"*Teléfono:* {lead.phone_country_code or ''} {lead.phone_number or ''}".strip(),
        f"*Instagram:* {lead.instagram or '—'}",
        "",
        f"*Llegada:* {_format_date(lead.arrival_date)}",
        f"*Salida:* {_format_date(lead.departure_date)}",
        "",
        f"*Motivo estancia:* {lead.get_stay_reason_display() if lead.stay_reason else '—'}",
    ]
    if lead.stay_reason_detail:
        lines.append(f"*Detalle:* {lead.stay_reason_detail}")
    if lead.university:
        lines.append(f"*Universidad:* {lead.university}")
    if lead.degree:
        lines.append(f"*Carrera/Programa:* {lead.degree}")
    lines.extend([
        "",
        f"*Presupuesto estancia:* {lead.budget_stay or '—'}",
        f"*Ya tiene alojamiento en Chile:* {'Sí' if lead.has_accommodation_in_chile else 'No'}",
        f"*Quiere contacto Rumi:* {'Sí' if lead.wants_rumi4students_contact else 'No'}",
    ])
    extra = lead.extra_data or {}
    for key in HOUSING_EXTRA_KEYS:
        val = extra.get(key)
        if val is not None and str(val).strip():
            label = key.replace("_", " ").replace("accommodation help", "Rumi").title()
            lines.append(f"*{label}:* {val}")
    lines.extend(["", "—"])
    return "\n".join(lines)


def notify_rumi_housing_lead(lead: ErasmusLead) -> bool:
    """
    If the lead requested Rumi contact for housing, send a notification to the configured
    WhatsApp group with housing-relevant details only (no destinations/interests).

    Returns True if a message was sent, False otherwise (no config, inactive, or not applicable).
    """
    if not getattr(lead, "wants_rumi4students_contact", False):
        return False

    config = ErasmusPartnerNotificationConfig.objects.filter(
        slug=RUMI_HOUSING_SLUG, is_active=True
    ).select_related("whatsapp_chat").first()

    if not config or not config.whatsapp_chat:
        logger.debug("[Rumi] No active group configured for rumi_housing; skip notification.")
        return False

    if config.whatsapp_chat.type != "group":
        logger.warning("[Rumi] Configured chat %s is not a group; skip.", config.whatsapp_chat_id)
        return False

    message = _format_rumi_housing_message(lead)
    try:
        from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
        service = WhatsAppWebService()
        service.send_message("", message, group_id=config.whatsapp_chat.chat_id)
        logger.info("[Rumi] Sent housing notification for lead %s to group %s", lead.id, config.whatsapp_chat.chat_id)
        return True
    except Exception as e:
        logger.exception("[Rumi] Failed to send housing notification for lead %s: %s", lead.id, e)
        return False


def _format_instance_label(inst: ErasmusActivityInstance) -> str:
    """Short label for the instance (date or month/label)."""
    if inst.scheduled_date:
        return inst.scheduled_date.strftime("%d/%m/%Y")
    if inst.scheduled_label_es:
        return inst.scheduled_label_es
    if inst.scheduled_month and inst.scheduled_year:
        return f"{inst.scheduled_month}/{inst.scheduled_year}"
    return str(inst.id)


def _format_activity_inscription_message(
    lead: ErasmusLead,
    instance: ErasmusActivityInstance,
    total_inscribed: int,
) -> str:
    """Build WhatsApp message for new activity inscription."""
    act = instance.activity
    activity_title = act.title_es or act.title_en or str(act.id)
    instance_label = _format_instance_label(instance)
    lines = [
        "📋 *Nueva inscripción – Actividad Erasmus*",
        "",
        f"*Actividad:* {activity_title}",
        f"*Fecha:* {instance_label}",
        "",
        f"*Persona:* {lead.first_name or ''} {lead.last_name or ''}".strip(),
        f"*Teléfono:* {lead.phone_country_code or ''} {lead.phone_number or ''}".strip(),
        f"*Email:* {lead.email or '—'}",
        "",
        f"*Total inscritos en esta fecha:* {total_inscribed}",
        "",
        "—",
    ]
    return "\n".join(lines)


def notify_activity_inscription(lead: ErasmusLead, instance: ErasmusActivityInstance) -> int:
    """
    When a lead has just expressed interest in this activity instance, notify all
    configured groups for this activity. Message includes new person + total inscribed for that instance.

    Returns the number of groups notified.
    """
    activity = instance.activity
    configs = ErasmusActivityNotificationConfig.objects.filter(
        activity=activity,
        is_active=True,
    ).select_related("whatsapp_chat")

    if not configs:
        logger.debug("[ActivityNotify] No configs for activity %s; skip.", activity.id)
        return 0

    total_inscribed = ErasmusLead.objects.filter(
        interested_experiences__contains=[str(instance.id)]
    ).count()

    message = _format_activity_inscription_message(lead, instance, total_inscribed)
    sent = 0
    try:
        from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
        service = WhatsAppWebService()
        for config in configs:
            if not config.whatsapp_chat or config.whatsapp_chat.type != "group":
                continue
            try:
                service.send_message("", message, group_id=config.whatsapp_chat.chat_id)
                sent += 1
                logger.info(
                    "[ActivityNotify] Sent inscription notification for lead %s instance %s to group %s",
                    lead.id, instance.id, config.whatsapp_chat.chat_id,
                )
            except Exception as e:
                logger.exception(
                    "[ActivityNotify] Failed to send to group %s: %s",
                    config.whatsapp_chat.chat_id, e,
                )
    except Exception as e:
        logger.exception("[ActivityNotify] Failed: %s", e)
    return sent


def send_activity_instance_whatsapp_to_lead(lead: ErasmusLead, instance: ErasmusActivityInstance) -> bool:
    """
    Send the instance's configured message to the person who just registered (the lead).
    Used for Tuki's own activities: we only message the registrant, not groups.
    If this instance has whatsapp_message_es or whatsapp_message_en, send it to the lead's
    phone. Picks language by lead.form_locale (default es).

    Returns True if a message was sent, False otherwise.
    """
    msg_es = (getattr(instance, "whatsapp_message_es", "") or "").strip()
    msg_en = (getattr(instance, "whatsapp_message_en", "") or "").strip()
    message = msg_es or msg_en
    if not message:
        logger.debug("[ActivityNotify] No WhatsApp message for instance %s; skip send to lead.", instance.id)
        return False

    if (getattr(lead, "form_locale", "") or "es").lower().startswith("en") and msg_en:
        message = msg_en
    else:
        message = msg_es or msg_en

    phone = ((lead.phone_country_code or "").replace(" ", "") + (lead.phone_number or "").replace(" ", "")).strip()
    if len(phone) < 8:
        logger.warning("[ActivityNotify] Lead %s has no valid phone for WhatsApp.", lead.id)
        return False

    try:
        from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
        service = WhatsAppWebService()
        clean_phone = service.clean_phone_number(phone)
        if not clean_phone:
            return False
        if not clean_phone.startswith("56") and len(clean_phone) >= 9:
            clean_phone = "56" + clean_phone.lstrip("0")
        service.send_message(clean_phone, message)
        logger.info("[ActivityNotify] Sent instance WhatsApp message to lead %s for instance %s", lead.id, instance.id)
        return True
    except Exception as e:
        logger.exception("[ActivityNotify] Failed to send WhatsApp to lead %s: %s", lead.id, e)
        return False
