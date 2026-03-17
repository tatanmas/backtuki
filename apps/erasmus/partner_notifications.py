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
    Message supports placeholders: {{first_name}}, {{payment_link}}, {{activity_title}}, {{instance_label}},
    {{order_number}}, and {{field_key}} for each activity extra field (from registration extra_data).
    For paid activities, a payment link is created automatically and included in the message.
    Updates ErasmusActivityPaymentLink.link_sent_at / link_sent_via on success, link_send_error on failure.

    Returns True if a message was sent, False otherwise.
    """
    from django.utils import timezone

    from apps.erasmus.models import ErasmusActivityPaymentLink, ErasmusActivityInstanceRegistration
    from apps.erasmus.payment_link_service import build_inscription_message

    extra_data = None
    reg = ErasmusActivityInstanceRegistration.objects.filter(lead=lead, instance=instance).first()
    if reg and reg.extra_data:
        extra_data = reg.extra_data
    order_number = None
    link = ErasmusActivityPaymentLink.objects.filter(lead=lead, instance=instance).first()
    if link and getattr(link, "order", None):
        order_number = getattr(link.order, "order_number", None) or ""
    message, _ = build_inscription_message(
        lead, instance, extra_data=extra_data, order_number=order_number
    )
    if not message or not message.strip():
        logger.debug("[ActivityNotify] No WhatsApp message for instance %s; skip send to lead.", instance.id)
        return False

    phone = ((lead.phone_country_code or "").replace(" ", "") + (lead.phone_number or "").replace(" ", "")).strip()
    # Prefer order.phone when available (single source of truth for "person who bought")
    link = ErasmusActivityPaymentLink.objects.filter(lead=lead, instance=instance).select_related("order").first()
    order = getattr(link, "order", None) if link else None
    if order and getattr(order, "phone", None) and str(order.phone).strip():
        order_phone = str(order.phone).replace(" ", "").strip()
        if len(order_phone) >= 8:
            phone = order_phone
    if len(phone) < 8:
        logger.warning("[ActivityNotify] Lead %s has no valid phone for WhatsApp.", lead.id)
        return False

    # Resolve flow_id for flow tracing (link already loaded above)
    order = getattr(link, "order", None) if link else None
    flow_id = str(order.flow_id) if order and getattr(order, "flow_id", None) else None

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
        if link:
            link.link_sent_at = timezone.now()
            link.link_sent_via = "automatic"
            link.link_send_error = None
            link.save(update_fields=["link_sent_at", "link_sent_via", "link_send_error"])
        # Trazabilidad: registrar en el flow que se envió el mensaje (link de pago / confirmación)
        if flow_id:
            try:
                from core.flow_logger import FlowLogger
                flow_logger = FlowLogger.from_flow_id(flow_id)
                if flow_logger:
                    flow_logger.log_event(
                        "CUSTOMER_MESSAGE_PAYMENT_LINK_SENT",
                        source="api",
                        status="success",
                        message=f"WhatsApp enviado a lead (actividad Erasmus, instance {instance.id})",
                        metadata={"lead_id": str(lead.id), "instance_id": str(instance.id)},
                    )
            except Exception as flog:
                logger.warning("[ActivityNotify] FlowLogger CUSTOMER_MESSAGE_PAYMENT_LINK_SENT: %s", flog)
        return True
    except Exception as e:
        logger.exception("[ActivityNotify] Failed to send WhatsApp to lead %s: %s", lead.id, e)
        if link:
            link.link_send_error = (str(e) or "Error al enviar")[:255]
            link.save(update_fields=["link_send_error"])
        # Trazabilidad: registrar fallo en el flow para que Superadmin vea por qué falló
        if flow_id:
            try:
                from core.flow_logger import FlowLogger
                flow_logger = FlowLogger.from_flow_id(flow_id)
                if flow_logger:
                    flow_logger.log_event(
                        "WHATSAPP_MESSAGE_FAILED",
                        source="api",
                        status="failure",
                        message=f"Error al enviar WhatsApp a lead (actividad Erasmus): {e!s}",
                        metadata={"lead_id": str(lead.id), "instance_id": str(instance.id), "error": str(e)[:500]},
                    )
            except Exception as flog:
                logger.warning("[ActivityNotify] FlowLogger WHATSAPP_MESSAGE_FAILED: %s", flog)
        return False
