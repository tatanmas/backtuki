"""Shared helpers for accommodation views (superadmin & organizer)."""

from decimal import Decimal

from django.conf import settings as django_settings

from apps.accommodations.constants import ROOM_CATEGORIES
from apps.accommodations.serializers import _normalize_media_url
from apps.media.models import MediaAsset

PREDEFINED_ROOM_CATEGORIES = {c[0] for c in ROOM_CATEGORIES}


def optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def parse_date(s):
    """Parse YYYY-MM-DD or return None."""
    if not s or not isinstance(s, str):
        return None
    try:
        from datetime import datetime
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def bathrooms_from_data(data):
    """
    Resolve (full_bathrooms, half_bathrooms) from a dict (e.g. request data or JSON).
    Prefers full_bathrooms/half_bathrooms. Legacy: bathrooms (int → all full; float 4.5 → 4 full + 1 half).
    """
    if "full_bathrooms" in data or "half_bathrooms" in data:
        full = max(0, int(data.get("full_bathrooms", 1)))
        half = max(0, int(data.get("half_bathrooms", 0)))
        return full, half
    b = data.get("bathrooms", 1)
    if b is None:
        return 1, 0
    try:
        b = float(b)
    except (TypeError, ValueError):
        return 1, 0
    if b <= 0:
        return 0, 0
    if b == int(b):
        return max(0, int(b)), 0
    full = int(b)
    half = 1
    return max(0, full), max(0, half)


def build_gallery_items_with_urls(acc, request=None):
    """
    Return gallery_items with image_url and is_principal for each.
    If gallery_items empty but gallery_media_ids present, build items from
    gallery_media_ids.
    """
    items = list(acc.gallery_items or [])
    if not items and acc.gallery_media_ids:
        items = [
            {"media_id": str(mid), "room_category": None, "sort_order": i, "is_principal": False}
            for i, mid in enumerate(acc.gallery_media_ids)
        ]
    if not items:
        return []

    ids = [str(it.get("media_id")) for it in items if it.get("media_id")]
    assets = MediaAsset.objects.filter(id__in=ids, deleted_at__isnull=True)
    asset_map = {str(a.id): a for a in assets if a.file}
    media_base = (getattr(django_settings, "BACKEND_URL", None) or "").rstrip("/")

    result = []
    for it in items:
        mid = it.get("media_id")
        if not mid:
            continue
        asset = asset_map.get(str(mid))
        url = ""
        if asset and asset.file:
            raw = asset.file.url
            if raw.startswith(("http://", "https://")):
                url = _normalize_media_url(raw)
            elif request:
                url = request.build_absolute_uri(raw)
            else:
                path = raw if raw.startswith("/") else f"/{raw.lstrip('/')}"
                url = f"{media_base}{path}" if media_base else raw
        result.append({
            "media_id": str(mid),
            "room_category": it.get("room_category"),
            "sort_order": it.get("sort_order", 0),
            "is_principal": bool(it.get("is_principal", False)),
            "image_url": url,
        })
    return result


def build_room_categories(acc):
    """Return predefined + custom room categories for the gallery."""
    predefined = [{"value": c[0], "label": c[1]} for c in ROOM_CATEGORIES]
    custom = [
        {"value": v, "label": v}
        for v in sorted(
            {it.get("room_category") for it in (acc.gallery_items or []) if it.get("room_category")}
            - PREDEFINED_ROOM_CATEGORIES
            - {"unclassified"}
        )
    ]
    return predefined + [{"value": "unclassified", "label": "Sin clasificar"}] + custom


def build_accommodation_detail_payload(acc, request=None, include_superadmin_fields=True):
    """Build the standard detail response dict for an accommodation."""
    gallery_items = build_gallery_items_with_urls(acc, request)
    room_categories = build_room_categories(acc)

    payload = {
        "id": str(acc.id),
        "title": acc.title,
        "slug": acc.slug,
        "description": acc.description or "",
        "short_description": acc.short_description or "",
        "status": acc.status,
        "property_type": acc.property_type or "cabin",
        "organizer_id": str(acc.organizer_id) if acc.organizer_id else None,
        "organizer_name": acc.organizer.name if acc.organizer else None,
        "location_name": acc.location_name or "",
        "location_address": acc.location_address or "",
        "latitude": float(acc.latitude) if acc.latitude is not None else None,
        "longitude": float(acc.longitude) if acc.longitude is not None else None,
        "city": acc.city or "",
        "country": acc.country or "",
        "guests": acc.guests,
        "bedrooms": acc.bedrooms,
        "full_bathrooms": acc.full_bathrooms,
        "half_bathrooms": acc.half_bathrooms,
        "bathrooms": (acc.full_bathrooms or 0) + (acc.half_bathrooms or 0),
        "beds": acc.beds,
        "price": float(acc.price or 0),
        "currency": acc.currency or "CLP",
        "amenities": acc.amenities if isinstance(acc.amenities, list) else [],
        "not_amenities": acc.not_amenities if isinstance(acc.not_amenities, list) else [],
        "photo_count": len(gallery_items),
        "gallery_items": gallery_items,
        "room_categories": room_categories,
    }

    if acc.rental_hub_id:
        payload["rental_hub_id"] = str(acc.rental_hub_id)
        payload["rental_hub_slug"] = acc.rental_hub.slug if acc.rental_hub else None
    if acc.hotel_id:
        payload["hotel_id"] = str(acc.hotel_id)
        payload["hotel_slug"] = acc.hotel.slug if acc.hotel else None
        payload["inherit_location_from_hotel"] = acc.inherit_location_from_hotel
        payload["inherit_amenities_from_hotel"] = acc.inherit_amenities_from_hotel
        payload["room_type_code"] = acc.room_type_code or ""

    payload["external_id"] = acc.external_id or ""
    payload["unit_type"] = acc.unit_type or ""
    payload["tower"] = acc.tower or ""
    payload["floor"] = acc.floor
    payload["unit_number"] = acc.unit_number or ""
    payload["square_meters"] = float(acc.square_meters) if acc.square_meters is not None else None
    payload["min_nights"] = acc.min_nights

    if include_superadmin_fields:
        payload["payment_model"] = acc.payment_model or ""
        payload["tuki_commission_rate"] = (
            float(acc.tuki_commission_rate) if acc.tuki_commission_rate is not None else None
        )
        payload["extra_charges"] = [
            {
                "id": str(e.id),
                "code": e.code,
                "name": e.name,
                "description": e.description or "",
                "charge_type": e.charge_type,
                "amount": float(e.amount),
                "currency": e.currency or "",
                "is_optional": e.is_optional,
                "default_quantity": e.default_quantity,
                "max_quantity": e.max_quantity,
                "is_active": e.is_active,
                "display_order": e.display_order,
            }
            for e in acc.extra_charges.order_by("display_order", "name")
        ]

    return payload
