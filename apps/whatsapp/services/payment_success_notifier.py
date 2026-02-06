"""
Notify operator and customer when payment succeeds for experience reservations.
"""
import logging
import secrets
from django.conf import settings
from django.core.cache import cache

from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
from apps.whatsapp.services.group_notification_service import GroupNotificationService
from apps.whatsapp.models import WhatsAppReservationRequest

logger = logging.getLogger(__name__)

ORGANIZER_TOKEN_CACHE_PREFIX = "organizer_reservation_token_"
ORGANIZER_TOKEN_TTL = 7 * 24 * 3600  # 7 days


def generate_organizer_reservation_token(reservation_id: str) -> str:
    """Generate short-lived token for organizer to view reservation. Returns token string."""
    token = secrets.token_urlsafe(32)
    cache_key = f"{ORGANIZER_TOKEN_CACHE_PREFIX}{token}"
    cache.set(cache_key, str(reservation_id), ORGANIZER_TOKEN_TTL)
    return token


def validate_organizer_reservation_token(token: str) -> str | None:
    """Validate token and return reservation_id if valid, else None."""
    if not token:
        return None
    cache_key = f"{ORGANIZER_TOKEN_CACHE_PREFIX}{token}"
    return cache.get(cache_key)


def notify_operator_payment_received(payment) -> bool:
    """
    Notify operator/group when experience payment succeeds.
    Message: name, date, time, paid full or deposit, reservation number, link with token.
    """
    try:
        order = payment.order
        if getattr(order, 'order_kind', 'event') != 'experience':
            return False
        exp_res = order.experience_reservation
        if not exp_res:
            return False

        wa_req = WhatsAppReservationRequest.objects.filter(
            linked_experience_reservation=exp_res
        ).select_related('experience', 'operator', 'whatsapp_message').first()
        if not wa_req:
            logger.info(f"No WhatsApp reservation linked to exp_res {exp_res.id}, skipping operator notify")
            return False

        experience = exp_res.experience
        instance = getattr(exp_res, 'instance', None)
        start_dt = instance.start_datetime if instance else None
        date_str = start_dt.strftime('%d/%m/%Y') if start_dt else 'N/A'
        time_str = start_dt.strftime('%H:%M') if start_dt else 'N/A'
        name = f"{exp_res.first_name or ''} {exp_res.last_name or ''}".strip() or 'Cliente'

        # deposit_only: paga diferencia en la experiencia; else: pagó todo
        is_deposit = getattr(experience, 'payment_model', None) == 'deposit_only'
        payment_desc = "Paga la diferencia en la experiencia" if is_deposit else "Pagó el total"

        token = generate_organizer_reservation_token(str(exp_res.id))
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')
        org_link = f"{frontend_url}/organizer/experiences/reservations/{exp_res.id}?token={token}"

        message = f"""✅ Pago recibido - Nueva reserva confirmada

Cliente: {name}
Fecha: {date_str}
Horario: {time_str}
Estado pago: {payment_desc}
N° Reserva: {exp_res.reservation_id}

Ver reserva: {org_link}"""

        group_info = GroupNotificationService.get_group_for_experience(experience)
        service = WhatsAppWebService()

        if group_info and group_info.get('chat_id'):
            service.send_message('', message, group_id=group_info['chat_id'])
            logger.info(f"Sent payment notification to group for reservation {exp_res.reservation_id}")
            return True
        operator = wa_req.operator
        if operator:
            phone = operator.whatsapp_number or operator.contact_phone
            if phone:
                service.send_message(phone, message)
                logger.info(f"Sent payment notification to operator for reservation {exp_res.reservation_id}")
                return True
        return False
    except Exception as e:
        logger.exception(f"Error notifying operator of payment: {e}")
        return False


def notify_customer_payment_success(payment, receipt_base64: str | None = None) -> bool:
    """
    Send WhatsApp to customer: thanks, success, optional receipt, magic link.
    """
    try:
        order = payment.order
        if getattr(order, 'order_kind', 'event') != 'experience':
            return False
        exp_res = order.experience_reservation
        if not exp_res:
            return False

        phone_raw = exp_res.phone or getattr(order, 'phone', '') or ''
        if not phone_raw:
            wa_req = WhatsAppReservationRequest.objects.filter(
                linked_experience_reservation=exp_res
            ).select_related('whatsapp_message').first()
            if wa_req and wa_req.whatsapp_message:
                phone_raw = getattr(wa_req.whatsapp_message, 'phone', '') or ''
        if not phone_raw:
            logger.warning("No customer phone for payment success notification")
            return False

        customer_phone = WhatsAppWebService.clean_phone_number(phone_raw)
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')
        magic_link = f"{frontend_url}/reservation/{order.order_number}?token={order.access_token}"

        message = f"""¡Gracias por tu compra! Fue realizada con éxito.

Ver el detalle de tu reserva: {magic_link}"""

        service = WhatsAppWebService()
        service.send_message(customer_phone, message)
        logger.info(f"Sent payment success to customer {customer_phone}")

        if receipt_base64:
            try:
                service.send_media(
                    customer_phone,
                    media_base64=receipt_base64,
                    mimetype='image/png',
                    filename='comprobante-reserva.png',
                    caption='Comprobante de tu reserva.'
                )
            except Exception as e:
                logger.warning(f"Could not send receipt image: {e}")
        return True
    except Exception as e:
        logger.exception(f"Error notifying customer of payment: {e}")
        return False
