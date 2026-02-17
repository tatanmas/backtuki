"""
Reusable test fixtures: checkout_data, constants.
Use in WhatsApp, payment, and accommodation tests.
"""

# Minimal valid checkout_data for accommodation (generation may accept; handler needs check_in/check_out).
CHECKOUT_DATA_ACCOMMODATION_MINIMAL = {
    "check_in": "2025-06-01",
    "check_out": "2025-06-03",
    "guests": 2,
    "pricing": {"total": 150000, "currency": "CLP"},
    "customer": {"name": "Test User"},
}

# Full checkout_data with contact/customer fields for _create_and_link_accommodation_reservation.
CHECKOUT_DATA_ACCOMMODATION_FULL = {
    "check_in": "2025-06-01",
    "check_out": "2025-06-03",
    "guests": 2,
    "pricing": {"total": 150000, "currency": "CLP"},
    "contact": {
        "first_name": "María",
        "last_name": "García",
        "email": "maria@example.com",
        "phone": "+56912345678",
    },
    "customer": {
        "name": "María García",
        "first_name": "María",
        "last_name": "García",
        "email": "maria@example.com",
        "phone": "+56912345678",
    },
}

# For reservation-by-code and payment: request statuses that allow payment.
RESERVATION_STATUSES_READY_FOR_PAYMENT = ("availability_confirmed", "confirmed")
