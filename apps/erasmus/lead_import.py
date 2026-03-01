"""
Shared logic for importing Erasmus leads from JSON.
Used by management command carga_subir_erasmus_leads and by Superadmin API create-from-json.
"""

from datetime import date

from django.utils.dateparse import parse_date

from .models import ErasmusLead, ErasmusExtraField


DEFAULT_BIRTH_DATE = date(2000, 1, 1)

REQUIRED_KEYS_FULL = (
    "first_name",
    "last_name",
    "phone_country_code",
    "phone_number",
    "stay_reason",
    "arrival_date",
    "departure_date",
)

REQUIRED_KEYS_INCOMPLETE = (
    "first_name",
    "last_name",
    "phone_country_code",
    "phone_number",
)


def parse_date_value(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parsed = parse_date(value)
        if parsed is None and value.strip():
            raise ValueError(f"Fecha inválida: {value!r}")
        return parsed or None
    return None


def normalize_lead(raw: dict, allow_incomplete: bool = False) -> dict:
    """Build a dict suitable for ErasmusLead with defaults for missing fields."""
    birth = parse_date_value(raw.get("birth_date"))
    arrival = parse_date_value(raw.get("arrival_date"))
    departure = parse_date_value(raw.get("departure_date"))

    if not birth:
        birth = DEFAULT_BIRTH_DATE if not allow_incomplete else None
    if not allow_incomplete:
        if not arrival:
            raise ValueError("arrival_date es obligatorio")
        if not departure:
            raise ValueError("departure_date es obligatorio")
        if departure < arrival:
            raise ValueError("departure_date debe ser posterior a arrival_date")
    else:
        if arrival and departure and departure < arrival:
            raise ValueError("departure_date debe ser posterior a arrival_date")

    stay_reason = (raw.get("stay_reason") or "").strip().lower()
    if stay_reason not in ("university", "practicas", "other"):
        if allow_incomplete:
            stay_reason = "other"
        else:
            raise ValueError("stay_reason debe ser university, practicas u other")

    extra_data = raw.get("extra_data")
    if not isinstance(extra_data, dict):
        extra_data = {}
    active_extra_keys = set(
        ErasmusExtraField.objects.filter(is_active=True).values_list("field_key", flat=True)
    )
    if active_extra_keys:
        extra_data = {k: v for k, v in extra_data.items() if k in active_extra_keys}

    email = (raw.get("email") or "").strip() or None
    source_slug = (raw.get("source_slug") or "").strip() or None
    form_locale = (raw.get("form_locale") or "es").strip().lower() or "es"
    if form_locale not in ("es", "en", "pt", "de", "it", "fr"):
        form_locale = "es"

    completion_status = "complete"
    if allow_incomplete and (birth is None or arrival is None or departure is None):
        completion_status = "pending_completion"

    return {
        "first_name": (raw.get("first_name") or "").strip()[:150],
        "last_name": (raw.get("last_name") or "").strip()[:150],
        "nickname": (raw.get("nickname") or "").strip()[:100],
        "birth_date": birth,
        "country": (raw.get("country") or "").strip()[:100],
        "city": (raw.get("city") or "").strip()[:150],
        "email": email,
        "phone_country_code": (raw.get("phone_country_code") or "").strip()[:10],
        "phone_number": (raw.get("phone_number") or "").strip()[:20],
        "instagram": (raw.get("instagram") or "").strip().lstrip("@")[:100],
        "stay_reason": stay_reason,
        "stay_reason_detail": (raw.get("stay_reason_detail") or "").strip()[:500],
        "university": (raw.get("university") or "").strip()[:255],
        "degree": (raw.get("degree") or "").strip()[:255],
        "arrival_date": arrival,
        "departure_date": departure,
        "budget_stay": (raw.get("budget_stay") or "").strip()[:200],
        "has_accommodation_in_chile": bool(raw.get("has_accommodation_in_chile", False)),
        "wants_rumi4students_contact": bool(raw.get("wants_rumi4students_contact", False)),
        "destinations": [str(x)[:100] for x in (raw.get("destinations") or []) if isinstance(raw.get("destinations"), list)],
        "interests": [str(x)[:100] for x in (raw.get("interests") or []) if isinstance(raw.get("interests"), list)],
        "source_slug": source_slug,
        "utm_source": (raw.get("utm_source") or "").strip()[:255] or None,
        "utm_medium": (raw.get("utm_medium") or "").strip()[:255] or None,
        "utm_campaign": (raw.get("utm_campaign") or "").strip()[:255] or None,
        "form_locale": form_locale,
        "extra_data": extra_data,
        "accept_tc_erasmus": bool(raw.get("accept_tc_erasmus", False)),
        "accept_privacy_erasmus": bool(raw.get("accept_privacy_erasmus", False)),
        "consent_email": bool(raw.get("consent_email", False)),
        "consent_whatsapp": bool(raw.get("consent_whatsapp", False)),
        "consent_share_providers": bool(raw.get("consent_share_providers", False)),
        "completion_status": completion_status,
    }
