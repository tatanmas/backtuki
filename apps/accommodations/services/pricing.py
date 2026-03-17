"""
Accommodation pricing service (cobros adicionales v1.5).
Single source of truth: calculates base + mandatory + optional extras.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.utils.translation import gettext_lazy as _

from apps.accommodations.models import Accommodation, AccommodationExtraCharge


class AccommodationPricingError(Exception):
    """Raised when pricing calculation fails (invalid input). Caller should return 400."""

    def __init__(self, message, code=None):
        self.message = message
        self.code = code
        super().__init__(message)


def _quantize_currency(value: Decimal, currency: str) -> Decimal:
    """Round to 0 decimals for CLP, 2 for USD/EUR."""
    if currency == "CLP":
        return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ensure_decimal(val):
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    return Decimal(str(val))


def calculate_accommodation_pricing(
    accommodation_id,
    check_in,
    check_out,
    guests,
    selected_options,
):
    """
    Calculate pricing snapshot for an accommodation reservation.

    Args:
        accommodation_id: UUID of the Accommodation.
        check_in: date or ISO date string (YYYY-MM-DD).
        check_out: date or ISO date string.
        guests: int >= 1.
        selected_options: list of {"code": str, "quantity": int} for optional extras only.

    Returns:
        dict suitable for pricing_snapshot: snapshot_version, nights, check_in, check_out,
        guests, currency, base, extras (list), total. Numeric values as float for JSON.

    Raises:
        AccommodationPricingError: invalid dates, guests, min_nights, or selected_options.
    """
    try:
        accommodation = Accommodation.objects.get(id=accommodation_id)
    except Accommodation.DoesNotExist:
        raise AccommodationPricingError(_("Accommodation not found"))

    if isinstance(check_in, str):
        try:
            check_in = date.fromisoformat(check_in)
        except (ValueError, TypeError):
            raise AccommodationPricingError(_("Invalid check_in date"))
    if isinstance(check_out, str):
        try:
            check_out = date.fromisoformat(check_out)
        except (ValueError, TypeError):
            raise AccommodationPricingError(_("Invalid check_out date"))

    if not check_in or not check_out:
        raise AccommodationPricingError(_("check_in and check_out are required"))
    if check_out <= check_in:
        raise AccommodationPricingError(_("check_out must be after check_in"))

    nights = (check_out - check_in).days
    if nights < 1:
        raise AccommodationPricingError(_("At least one night required"))

    min_nights = accommodation.get_effective_min_nights()
    if min_nights is not None and nights < min_nights:
        raise AccommodationPricingError(
            _("Minimum %(min)s nights required") % {"min": min_nights}
        )

    if not isinstance(guests, int) or guests < 1:
        raise AccommodationPricingError(_("guests must be at least 1"))

    currency = (accommodation.currency or "CLP").strip() or "CLP"
    price_per_night = _ensure_decimal(accommodation.price or 0)
    if price_per_night < 0:
        price_per_night = Decimal("0")

    base_subtotal = _quantize_currency(price_per_night * nights, currency)
    acc_currency = currency

    extras_list = []
    extras_total = Decimal("0")

    # Mandatory extras: is_active=True, is_optional=False. Quantity by logic: per_stay=1, per_night=nights
    mandatory = AccommodationExtraCharge.objects.filter(
        accommodation=accommodation,
        is_active=True,
        is_optional=False,
    ).order_by("display_order", "name")

    for extra in mandatory:
        extra_currency = (extra.currency or acc_currency).strip() or acc_currency
        if extra_currency != acc_currency:
            raise AccommodationPricingError(
                _("Extra %(code)s has different currency; not allowed in v1") % {"code": extra.code}
            )
        amount = _ensure_decimal(extra.amount)
        if extra.charge_type == "per_stay":
            qty = 1
        else:
            qty = nights
        line_total = _quantize_currency(amount * qty, extra_currency)
        extras_total += line_total
        extras_list.append({
            "code": extra.code,
            "name": extra.name,
            "charge_type": extra.charge_type,
            "quantity": qty,
            "unit_amount": float(amount),
            "total": float(line_total),
        })

    # Optional extras from selected_options: validate each code and quantity, then add
    selected_options = selected_options or []
    if not isinstance(selected_options, list):
        raise AccommodationPricingError(_("selected_options must be a list"))

    for item in selected_options:
        if not isinstance(item, dict):
            raise AccommodationPricingError(_("Each selected_options item must be {code, quantity}"))
        code = item.get("code")
        quantity = item.get("quantity")
        if code is None or code == "":
            raise AccommodationPricingError(_("selected_options item missing code"))
        try:
            qty = int(quantity)
        except (TypeError, ValueError):
            raise AccommodationPricingError(
                _("Invalid quantity for extra %(code)s") % {"code": code}
            )
        if qty < 1:
            raise AccommodationPricingError(
                _("Quantity for %(code)s must be at least 1") % {"code": code}
            )

        try:
            extra = AccommodationExtraCharge.objects.get(
                accommodation=accommodation,
                code=code,
            )
        except AccommodationExtraCharge.DoesNotExist:
            raise AccommodationPricingError(
                _("Invalid or non-optional extra code: %(code)s") % {"code": code}
            )

        if not extra.is_active:
            raise AccommodationPricingError(
                _("Invalid or non-optional extra code: %(code)s") % {"code": code}
            )
        if not extra.is_optional:
            raise AccommodationPricingError(
                _("Invalid or non-optional extra code: %(code)s") % {"code": code}
            )

        if extra.max_quantity is not None and qty > extra.max_quantity:
            raise AccommodationPricingError(
                _("Quantity for %(code)s exceeds max_quantity") % {"code": code}
            )

        extra_currency = (extra.currency or acc_currency).strip() or acc_currency
        if extra_currency != acc_currency:
            raise AccommodationPricingError(
                _("Extra %(code)s has different currency; not allowed in v1") % {"code": code}
            )

        amount = _ensure_decimal(extra.amount)
        if extra.charge_type == "per_stay":
            line_total = _quantize_currency(amount * qty, extra_currency)
        else:
            line_total = _quantize_currency(amount * qty * nights, extra_currency)
        extras_total += line_total
        extras_list.append({
            "code": extra.code,
            "name": extra.name,
            "charge_type": extra.charge_type,
            "quantity": qty,
            "unit_amount": float(amount),
            "total": float(line_total),
        })

    total = _quantize_currency(base_subtotal + extras_total, currency)

    snapshot = {
        "snapshot_version": 1,
        "nights": nights,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "guests": guests,
        "currency": currency,
        "base": {
            "price_per_night": float(price_per_night),
            "subtotal": float(base_subtotal),
        },
        "extras": extras_list,
        "total": float(total),
    }
    return snapshot
