# Shared test infrastructure: fixtures, factories, tags.
from core.testing.fixtures import (
    CHECKOUT_DATA_ACCOMMODATION_MINIMAL,
    CHECKOUT_DATA_ACCOMMODATION_FULL,
    RESERVATION_STATUSES_READY_FOR_PAYMENT,
)
from core.testing.factories import (
    create_organizer,
    create_accommodation,
    create_whatsapp_chat,
    create_tour_operator,
    create_accommodation_operator_binding,
    create_whatsapp_message,
    create_reservation_code_for_accommodation,
    create_reservation_code_raw,
    create_whatsapp_reservation_request,
    create_accommodation_reservation,
    create_order_accommodation,
)

__all__ = [
    "CHECKOUT_DATA_ACCOMMODATION_MINIMAL",
    "CHECKOUT_DATA_ACCOMMODATION_FULL",
    "RESERVATION_STATUSES_READY_FOR_PAYMENT",
    "create_organizer",
    "create_accommodation",
    "create_whatsapp_chat",
    "create_tour_operator",
    "create_accommodation_operator_binding",
    "create_whatsapp_message",
    "create_reservation_code_for_accommodation",
    "create_reservation_code_raw",
    "create_whatsapp_reservation_request",
    "create_accommodation_reservation",
    "create_order_accommodation",
]
