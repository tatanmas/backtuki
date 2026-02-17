"""
Shared test factories (plain helpers, no factory_boy).
Create Accommodation, AccommodationReservation, WhatsAppReservationCode, WhatsAppReservationRequest, Order, etc.
"""
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from apps.organizers.models import Organizer
from apps.accommodations.models import Accommodation, AccommodationReservation
from apps.whatsapp.models import (
    WhatsAppReservationCode,
    WhatsAppReservationRequest,
    TourOperator,
    WhatsAppChat,
    WhatsAppMessage,
    AccommodationOperatorBinding,
)
from core.testing.fixtures import CHECKOUT_DATA_ACCOMMODATION_FULL


def create_organizer(name="Test Org", slug="test-org"):
    """Create an Organizer for tests. Defaults: name Test Org, slug test-org."""
    return Organizer.objects.create(name=name, slug=slug)


def create_accommodation(organizer=None, title="Test Cabin", slug="test-cabin", status="published", **kwargs):
    """Create published Accommodation; creates organizer if not provided. kwargs override defaults."""
    if organizer is None:
        organizer = create_organizer()
    defaults = {
        "title": title,
        "slug": slug,
        "organizer": organizer,
        "status": status,
        "guests": 4,
        "price": Decimal("50000"),
        "currency": "CLP",
    }
    defaults.update(kwargs)
    return Accommodation.objects.create(**defaults)


def create_whatsapp_chat(chat_id="120363000000@g.us", name="Test Group", type="group"):
    """Create a WhatsAppChat (e.g. group) for operator bindings and notifications."""
    return WhatsAppChat.objects.create(chat_id=chat_id, name=name, type=type)


def create_tour_operator(name="Test Operator", default_whatsapp_group=None):
    """Create a TourOperator; optional default_whatsapp_group for notifications."""
    return TourOperator.objects.create(
        name=name,
        default_whatsapp_group=default_whatsapp_group,
    )


def create_accommodation_operator_binding(accommodation, tour_operator, is_active=True):
    """Link accommodation to a tour operator (for WhatsApp group resolution)."""
    return AccommodationOperatorBinding.objects.create(
        accommodation=accommodation,
        tour_operator=tour_operator,
        is_active=is_active,
    )


def create_whatsapp_message(phone="+56912345678", content="RES-ABC123", chat=None, whatsapp_id=None):
    """Create an inbound WhatsAppMessage (type=in, unique whatsapp_id, timestamp=now)."""
    import uuid
    return WhatsAppMessage.objects.create(
        whatsapp_id=whatsapp_id or f"msg-{uuid.uuid4().hex[:12]}",
        phone=phone,
        type="in",
        content=content,
        timestamp=timezone.now(),
        chat=chat,
    )


def create_reservation_code_for_accommodation(
    accommodation,
    checkout_data=None,
    status="pending",
    linked_reservation=None,
    expires_at=None,
):
    """Create WhatsAppReservationCode via ReservationCodeGenerator; optional status/linked/expires override."""
    from apps.whatsapp.services.reservation_code_generator import ReservationCodeGenerator

    if checkout_data is None:
        checkout_data = CHECKOUT_DATA_ACCOMMODATION_FULL.copy()
    if expires_at is None:
        expires_at = timezone.now() + timedelta(hours=24)
    code_obj = ReservationCodeGenerator.generate_code_for_accommodation(
        str(accommodation.id), checkout_data
    )
    if status != "pending":
        code_obj.status = status
        code_obj.save(update_fields=["status"])
    if linked_reservation is not None:
        code_obj.linked_reservation = linked_reservation
        code_obj.save(update_fields=["linked_reservation"])
    if expires_at != code_obj.expires_at:
        code_obj.expires_at = expires_at
        code_obj.save(update_fields=["expires_at"])
    return code_obj


def create_reservation_code_raw(
    code="RES-TEST-20250601-ABCD1234",
    accommodation=None,
    checkout_data=None,
    status="pending",
    linked_reservation=None,
    expires_at=None,
):
    """Create WhatsAppReservationCode directly (for expired/already-linked tests)."""
    if checkout_data is None:
        checkout_data = CHECKOUT_DATA_ACCOMMODATION_FULL.copy()
    if expires_at is None:
        expires_at = timezone.now() + timedelta(hours=24)
    return WhatsAppReservationCode.objects.create(
        code=code,
        experience=None,
        accommodation=accommodation,
        checkout_data=checkout_data,
        status=status,
        linked_reservation=linked_reservation,
        expires_at=expires_at,
    )


def create_whatsapp_reservation_request(
    whatsapp_message,
    accommodation=None,
    experience=None,
    tour_code="RES-TEST-00000000-ABCD1234",
    status="operator_notified",
    linked_accommodation_reservation=None,
    **kwargs,
):
    """Create WhatsAppReservationRequest (accommodation or experience, status, optional linked_accommodation_reservation)."""
    defaults = {
        "whatsapp_message": whatsapp_message,
        "tour_code": tour_code,
        "passengers": 2,
        "operator": None,
        "experience": experience,
        "accommodation": accommodation,
        "status": status,
        "timeout_at": timezone.now() + timedelta(minutes=30),
        "linked_accommodation_reservation": linked_accommodation_reservation,
    }
    defaults.update(kwargs)
    return WhatsAppReservationRequest.objects.create(**defaults)


def create_accommodation_reservation(
    accommodation,
    check_in=None,
    check_out=None,
    guests=2,
    total=Decimal("150000"),
    currency="CLP",
    first_name="Test",
    last_name="User",
    email="test@example.com",
    phone="+56912345678",
    status="pending",
):
    """Create AccommodationReservation with reservation_id ACC-<hex>; defaults for dates, guests, pricing."""
    from datetime import date
    import uuid

    if check_in is None:
        check_in = date(2025, 6, 1)
    if check_out is None:
        check_out = date(2025, 6, 3)
    reservation_id = f"ACC-{uuid.uuid4().hex[:12].upper()}"
    return AccommodationReservation.objects.create(
        reservation_id=reservation_id,
        accommodation=accommodation,
        status=status,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        total=total,
        currency=currency,
    )


def create_order_accommodation(accommodation_reservation, total=None, email=None, currency="CLP", **kwargs):
    """Create Order with order_kind=accommodation, linked to accommodation_reservation; status pending."""
    from apps.events.models import Order

    total = total or accommodation_reservation.total
    email = email or accommodation_reservation.email
    return Order.objects.create(
        order_kind="accommodation",
        accommodation_reservation=accommodation_reservation,
        experience_reservation=None,
        event=None,
        email=email,
        first_name=accommodation_reservation.first_name,
        last_name=accommodation_reservation.last_name,
        phone=accommodation_reservation.phone or "",
        total=total,
        subtotal=total,
        service_fee=0,
        discount=0,
        taxes=0,
        currency=currency or getattr(accommodation_reservation, "currency", "CLP"),
        status="pending",
        **kwargs,
    )
