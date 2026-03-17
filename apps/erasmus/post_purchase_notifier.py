"""
Notify customer (WhatsApp + email) when an Erasmus activity inscription is marked as paid (manual/efectivo).
Same message as post-purchase for platform payment: post_purchase_message with placeholders.
"""
import logging
from typing import Optional

from apps.erasmus.email_context import get_post_purchase_message_personalized
from apps.erasmus.email_sender import send_erasmus_activity_confirmation_email_optimized
from apps.erasmus.models import ErasmusActivityPaymentLink, ErasmusActivityInstanceRegistration

logger = logging.getLogger(__name__)


def notify_manual_payment_success(lead, instance) -> None:
    """
    After marking an inscription as paid (efectivo/manual): send post-purchase message by WhatsApp
    and send confirmation email if there is an Order (from payment link).
    Message supports {{field_key}} from registration extra_data.
    Does not raise; logs errors.
    """
    try:
        link = ErasmusActivityPaymentLink.objects.filter(
            lead=lead,
            instance=instance,
        ).select_related("lead", "instance", "instance__activity").first()

        order = getattr(link, "order", None) if link else None
        order_number = (getattr(order, "order_number", "") or "Pago registrado") if order else "Pago registrado"

        extra_data = None
        reg = ErasmusActivityInstanceRegistration.objects.filter(lead=lead, instance=instance).first()
        if reg and getattr(reg, "extra_data", None):
            extra_data = reg.extra_data

        if order and order.status != "paid":
            order.status = "paid"
            order.save(update_fields=["status"])
            try:
                result = send_erasmus_activity_confirmation_email_optimized(
                    order_id=str(order.id),
                    to_email=(getattr(lead, "email", None) or "").strip() or order.email,
                    flow_id=str(order.flow_id) if getattr(order, "flow_id", None) else None,
                )
                if result.get("status") != "success":
                    logger.warning(
                        "Erasmus manual payment: email send failed for order %s: %s",
                        order.order_number,
                        result.get("error"),
                    )
            except Exception as e:
                logger.warning("Erasmus manual payment: email send failed: %s", e, exc_info=True)

        message = get_post_purchase_message_personalized(
            lead, instance, order_number=order_number, extra_data=extra_data
        )
        if not message:
            message = (
                f"Hola {(getattr(lead, 'first_name', None) or '').strip() or 'Participante'}, "
                "tu pago ha sido registrado correctamente. ¡Gracias!"
            )

        phone_raw = (getattr(lead, "phone_country_code", "") or "").strip() + (getattr(lead, "phone_number", "") or "").strip()
        if not phone_raw:
            logger.warning("Erasmus manual payment: no phone for lead %s, skipping WhatsApp", getattr(lead, "id", ""))
            return

        from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
        service = WhatsAppWebService()
        clean_phone = service.clean_phone_number(phone_raw)
        if clean_phone:
            service.send_message(clean_phone, message)
            logger.info("Erasmus manual payment: WhatsApp sent to %s for lead %s", clean_phone[:8], getattr(lead, "id", ""))
            # Trazabilidad: registrar en el flow que se envió mensaje post-pago por WhatsApp
            if order and getattr(order, "flow_id", None):
                try:
                    from core.flow_logger import FlowLogger
                    fl = FlowLogger.from_flow_id(str(order.flow_id))
                    if fl:
                        fl.log_event(
                            "CUSTOMER_MESSAGE_PAYMENT_SUCCESS_SENT",
                            source="api",
                            status="success",
                            message="WhatsApp post-pago enviado (pago manual/efectivo)",
                            metadata={"lead_id": str(getattr(lead, "id", "")), "order_number": getattr(order, "order_number", "")},
                        )
                except Exception as flog:
                    logger.warning("Erasmus manual payment: FlowLogger CUSTOMER_MESSAGE_PAYMENT_SUCCESS_SENT: %s", flog)
    except Exception as e:
        logger.warning("Erasmus manual payment notify failed: %s", e, exc_info=True)
        # Trazabilidad: registrar fallo de envío WhatsApp en el flow si hay orden con flow
        if order and getattr(order, "flow_id", None):
            try:
                from core.flow_logger import FlowLogger
                fl = FlowLogger.from_flow_id(str(order.flow_id))
                if fl:
                    fl.log_event(
                        "WHATSAPP_MESSAGE_FAILED",
                        source="api",
                        status="failure",
                        message=f"WhatsApp post-pago falló: {e!s}",
                        metadata={"error": str(e)[:500]},
                    )
            except Exception:
                pass
