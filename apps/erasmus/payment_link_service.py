"""
Get or create payment link for an Erasmus activity inscription (lead + instance).
Used when sending the post-registration WhatsApp message (with {{payment_link}})
and when the organizer copies "mensaje adicional" from the inscritos list.

Enterprise: atomic creation (link + order in one transaction), single place for
all link creation so public view and notifications use the same logic.

Free activities: get_or_create_order_for_free_inscription creates a zero-amount
link + order so the same flow (WhatsApp send tracking, "Ver pedido") works.
"""
import re
import secrets
import logging
from decimal import Decimal
from typing import Optional, Tuple

from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone

from .models import ErasmusActivityPaymentLink, ErasmusActivityInscriptionPayment

logger = logging.getLogger(__name__)


def get_frontend_url() -> str:
    return (getattr(settings, "FRONTEND_URL", "http://localhost:8080") or "http://localhost:8080").rstrip("/")


def get_or_create_payment_link(
    lead, instance
) -> Tuple[Optional[ErasmusActivityPaymentLink], Optional[str], bool]:
    """
    Get or create a payment link for this lead + instance. Creates ErasmusActivityPaymentLink
    and Order in a single atomic transaction. Returns (link, payment_url, created) or
    (None, None, False) if activity is not paid / no price / already paid.

    Caller must ensure lead is inscribed in this instance (interested_experiences contains instance.id).
    """
    from apps.events.models import Order

    activity = instance.activity
    if not getattr(activity, "is_paid", False):
        return None, None, False
    amount = getattr(activity, "price", None)
    if amount is None or amount <= 0:
        return None, None, False
    if ErasmusActivityInscriptionPayment.objects.filter(lead=lead, instance=instance).exists():
        return None, None, False

    existing = ErasmusActivityPaymentLink.objects.filter(lead=lead, instance=instance).first()
    if existing:
        if existing.expires_at and timezone.now() > existing.expires_at:
            with transaction.atomic():
                existing.delete()
                existing = None
        elif getattr(existing, "order", None) and existing.order.status == "paid":
            return None, None, False
        elif getattr(existing, "order", None) and existing.order.status == "pending":
            frontend_url = get_frontend_url()
            url = f"{frontend_url}/checkout/erasmus-activity?token={existing.token}"
            return existing, url, False

    # Create link + order in one transaction (no orphan link or order).
    # On IntegrityError (concurrent create for same lead+instance), fetch and return existing.
    try:
        with transaction.atomic():
            token_str = secrets.token_urlsafe(32)[:48]
            link = ErasmusActivityPaymentLink(
                lead=lead,
                instance=instance,
                amount=amount,
                currency="CLP",
                token=token_str,
                expires_at=timezone.now() + timezone.timedelta(days=7),
            )
            link.save()

            email = (lead.email or "").strip() or "inscrito@tuki.local"
            phone = ((lead.phone_country_code or "") + (lead.phone_number or ""))[:20]
            Order.objects.create(
                user=None,
                email=email,
                first_name=(lead.first_name or "")[:100],
                last_name=(lead.last_name or "")[:100],
                phone=phone,
                total=amount,
                subtotal=amount,
                service_fee=Decimal("0"),
                discount=Decimal("0"),
                taxes=Decimal("0"),
                order_kind="erasmus_activity",
                erasmus_activity_payment_link=link,
                status="pending",
            )
        order = Order.objects.get(erasmus_activity_payment_link=link)
        from apps.erasmus.flow_service import start_flow_for_payment_link
        start_flow_for_payment_link(link, order)
        frontend_url = get_frontend_url()
        url = f"{frontend_url}/checkout/erasmus-activity?token={token_str}"
        return link, url, True
    except IntegrityError:
        # Unique (lead, instance): another request created the link concurrently
        existing = ErasmusActivityPaymentLink.objects.filter(lead=lead, instance=instance).first()
        if existing and getattr(existing, "order", None) and existing.order.status == "pending":
            frontend_url = get_frontend_url()
            url = f"{frontend_url}/checkout/erasmus-activity?token={existing.token}"
            return existing, url, False
        if existing:
            return existing, None, False
        raise


def get_or_create_payment_link_url(lead, instance) -> Optional[str]:
    """Convenience: returns only the URL (for WhatsApp message, etc.)."""
    _, url, _ = get_or_create_payment_link(lead, instance)
    return url


def get_or_create_order_for_free_inscription(lead, instance):
    """
    For free Erasmus activities: get or create an order (and link) so the same
    flow applies: flow tracking, WhatsApp send status (link_sent_at / link_send_error),
    and "Ver pedido" in the inscritos list. Order has total=0 and status='paid'.

    Call only when lead is inscribed in instance and activity is not paid
    (is_paid=False or price is null/0). Returns (link, order) or (None, None).
    """
    from apps.events.models import Order
    from apps.erasmus.flow_service import start_flow_for_payment_link

    activity = instance.activity
    if getattr(activity, "is_paid", False):
        amount = getattr(activity, "price", None)
        if amount is not None and amount > 0:
            return None, None

    existing = ErasmusActivityPaymentLink.objects.filter(
        lead=lead, instance=instance
    ).select_related("order").first()
    if existing and getattr(existing, "order", None):
        return existing, existing.order

    try:
        with transaction.atomic():
            token_str = secrets.token_urlsafe(32)[:48]
            link = ErasmusActivityPaymentLink(
                lead=lead,
                instance=instance,
                amount=Decimal("0"),
                currency="CLP",
                token=token_str,
                expires_at=None,
            )
            link.save()

            email = (lead.email or "").strip() or "inscrito@tuki.local"
            phone = ((lead.phone_country_code or "") + (lead.phone_number or ""))[:20]
            order = Order.objects.create(
                user=None,
                email=email,
                first_name=(lead.first_name or "")[:100],
                last_name=(lead.last_name or "")[:100],
                phone=phone,
                total=Decimal("0"),
                subtotal=Decimal("0"),
                service_fee=Decimal("0"),
                discount=Decimal("0"),
                taxes=Decimal("0"),
                order_kind="erasmus_activity",
                erasmus_activity_payment_link=link,
                status="paid",
            )
        start_flow_for_payment_link(link, order, is_free=True)
        return link, order
    except IntegrityError:
        existing = ErasmusActivityPaymentLink.objects.filter(
            lead=lead, instance=instance
        ).select_related("order").first()
        if existing and getattr(existing, "order", None):
            return existing, existing.order
        raise


def _format_instance_label(instance):
    """Short label for the instance (date or month/label)."""
    if instance.scheduled_date:
        return instance.scheduled_date.strftime("%d/%m/%Y")
    if getattr(instance, "scheduled_label_es", None):
        return instance.scheduled_label_es
    if getattr(instance, "scheduled_month", None) and getattr(instance, "scheduled_year", None):
        return f"{instance.scheduled_month}/{instance.scheduled_year}"
    return str(instance.id)


def build_inscription_message(lead, instance, payment_link_url=None, extra_data=None, order_number=None):
    """
    Build the WhatsApp message for this inscription, with placeholders replaced.
    Placeholders: {{first_name}}, {{payment_link}}, {{activity_title}}, {{instance_label}}, {{order_number}},
    and for each activity extra field: {{field_key}} (from extra_data).
    If payment_link_url is None and activity is paid, get_or_create_payment_link_url is called.
    """
    act = instance.activity
    first_name = (lead.first_name or "").strip() or "Participante"
    activity_title = act.title_es or act.title_en or str(act.id)
    instance_label = _format_instance_label(instance)

    if payment_link_url is None and getattr(act, "is_paid", False):
        payment_link_url = get_or_create_payment_link_url(lead, instance)
    payment_link = payment_link_url or ""
    order_num_str = (order_number or "").strip() or ""

    msg_es = (getattr(instance, "whatsapp_message_es", "") or "").strip()
    msg_en = (getattr(instance, "whatsapp_message_en", "") or "").strip()
    message = msg_es or msg_en
    if not message:
        message = f"Hola {first_name}, gracias por inscribirte en {activity_title} ({instance_label})."
        if payment_link:
            message += f"\n\nLink de pago: {payment_link}"

    message = (
        message.replace("{{first_name}}", first_name)
        .replace("{{payment_link}}", payment_link)
        .replace("{{activity_title}}", activity_title)
        .replace("{{instance_label}}", instance_label)
        .replace("{{order_number}}", order_num_str)
    )
    # Activity extra field metatags: {{field_key}} -> value from extra_data
    if extra_data and isinstance(extra_data, dict):
        for key, value in extra_data.items():
            if key and value is not None:
                message = message.replace("{{" + str(key) + "}}", str(value).strip())
    # Replace any remaining {{field_key}} for missing keys with empty string
    message = re.sub(r"\{\{[^}]+\}\}", lambda m: "", message)
    return message, payment_link_url or None
