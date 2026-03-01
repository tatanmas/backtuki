"""Serializers for accommodations API (formato que espera el frontend).
Robust: mismo patrón que destinos y experiencias — URLs absolutas con request host o BACKEND_URL.
"""

import re
from urllib.parse import urlparse

from django.conf import settings as django_settings
from rest_framework import serializers

from .models import Accommodation, AccommodationReview
from .constants import ROOM_CATEGORIES, ROOM_CATEGORY_LABELS


def _normalize_media_url(url):
    """Rewrite localhost/127.0.0.1 media URLs to BACKEND_URL (igual que landing_destinations)."""
    if not url or not isinstance(url, str):
        return url or ""
    if "localhost" not in url and "127.0.0.1" not in url:
        return url
    base = getattr(django_settings, "BACKEND_URL", None)
    if not base:
        return url
    base = base.rstrip("/")
    for prefix in ("http://localhost:8000/", "http://localhost/", "https://localhost:8000/", "https://localhost/"):
        if url.startswith(prefix):
            path = url[len(prefix) :].lstrip("/")
            return f"{base}/{path}" if path else base
    if "127.0.0.1" in url:
        path_match = re.search(r"https?://127\.0\.0\.1(?::\d+)?(/.+)?", url)
        if path_match:
            path = (path_match.group(1) or "").lstrip("/")
            return f"{base}/{path}" if path else base
    return url


def _absolute_media_url(relative_path, request=None):
    """Absolute URL for a relative media path (request host or BACKEND_URL)."""
    if not relative_path:
        return ""
    if relative_path.startswith(("http://", "https://")):
        return _normalize_media_url(relative_path)
    if request:
        return request.build_absolute_uri(relative_path if relative_path.startswith("/") else f"/{relative_path}")
    base = getattr(django_settings, "BACKEND_URL", None) or "http://localhost:8000"
    path = relative_path.lstrip("/")
    return f"{base.rstrip('/')}/{path}" if path else base


def _rewrite_media_url_to_request_host(url, request):
    """Rewrite media URL to request scheme+host (images load from same origin as API)."""
    if not url or not request:
        return url or ""
    parsed = urlparse(url)
    path = parsed.path or ""
    if not path:
        return url
    return request.build_absolute_uri(path)


def _build_images_from_gallery_items(acc, request=None):
    """
    Lista plana de URLs ordenada por sort_order global.
    Si algún item tiene is_principal=True, esa URL va primero (para card/listado).
    """
    from apps.media.models import MediaAsset

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

    resolved = []
    for it in items:
        mid = it.get("media_id")
        if not mid:
            continue
        asset = asset_map.get(str(mid))
        if not asset or not asset.file:
            continue
        url = _resolve_image_url_for_asset(asset, request)
        if not url:
            continue
        resolved.append({
            "url": url,
            "sort_order": it.get("sort_order", 0),
            "is_principal": bool(it.get("is_principal")),
        })

    resolved.sort(key=lambda x: x["sort_order"])
    urls = [r["url"] for r in resolved]
    principal_url = next((r["url"] for r in resolved if r["is_principal"]), None)
    if principal_url and urls and urls[0] != principal_url:
        urls = [principal_url] + [u for u in urls if u != principal_url]
    return urls


def _resolve_images(acc, request=None):
    """
    Lista de URLs de imagen: mismo patrón que destinos (landing_destinations/views.py).
    Orden global por sort_order; si is_principal en algún item, esa imagen va primero (card).
    """
    urls = _build_images_from_gallery_items(acc, request)
    if urls:
        return urls

    # Fallback: gallery_media_ids sin categorías, o legacy images
    urls = []
    media_base = (getattr(django_settings, "BACKEND_URL", None) or "").rstrip("/")

    # 1) Desde MediaAsset — igual que destinos: request.build_absolute_uri(a.file.url) si hay request
    if acc.gallery_media_ids:
        from apps.media.models import MediaAsset

        assets = MediaAsset.objects.filter(
            id__in=acc.gallery_media_ids,
            deleted_at__isnull=True,
        )
        asset_map = {str(a.id): a for a in assets if a.file}
        for eid in acc.gallery_media_ids:
            a = asset_map.get(str(eid))
            if a and a.file:
                raw = a.file.url
                if raw.startswith(("http://", "https://")):
                    url = _normalize_media_url(raw)
                elif request:
                    url = request.build_absolute_uri(raw)
                else:
                    path = raw if raw.startswith("/") else f"/{raw.lstrip('/')}"
                    url = f"{media_base}{path}" if media_base else _absolute_media_url(raw, None)
                if url:
                    urls.append(url)
    # 2) Fallback: acc.images (legacy o respaldo) — normalizar solo localhost; no reescribir URLs externas (GCS)
    for raw in acc.images or []:
        if not raw or not isinstance(raw, str):
            continue
        raw = _normalize_media_url(raw.strip())
        if not raw:
            continue
        if raw.startswith(("http://", "https://")):
            if "localhost" in raw or "127.0.0.1" in raw:
                path = urlparse(raw).path or ""
                if media_base and path:
                    raw = f"{media_base}{path}"
                elif request:
                    raw = _rewrite_media_url_to_request_host(raw, request)
            # Si es URL externa (p. ej. GCS), dejarla tal cual para que las fotos carguen
        else:
            path = raw if raw.startswith("/") else f"/{raw.lstrip('/')}"
            if media_base:
                raw = f"{media_base}{path}"
            elif request:
                raw = request.build_absolute_uri(path)
            else:
                raw = _absolute_media_url(path, None)
        if raw and raw not in urls:
            urls.append(raw)
    return urls


def _resolve_image_url_for_asset(asset, request=None):
    """Single MediaAsset URL (same logic as _resolve_images)."""
    if not asset or not asset.file:
        return ""
    raw = asset.file.url
    if raw.startswith(("http://", "https://")):
        return _normalize_media_url(raw)
    if request:
        return request.build_absolute_uri(raw)
    media_base = (getattr(django_settings, "BACKEND_URL", None) or "").rstrip("/")
    path = raw if raw.startswith("/") else f"/{raw.lstrip('/')}"
    return f"{media_base}{path}" if media_base else _absolute_media_url(raw, None)


def _build_photo_tour(acc, request=None):
    """
    Build photo_tour from gallery_items: list of { room_category, label, images }.
    Only include groups with at least one image. Order: ROOM_CATEGORIES; within group by sort_order.
    """
    from apps.media.models import MediaAsset

    items = list(acc.gallery_items or [])
    if not items and acc.gallery_media_ids:
        items = [
            {"media_id": str(mid), "room_category": None, "sort_order": i}
            for i, mid in enumerate(acc.gallery_media_ids)
        ]
    if not items:
        return []

    ids = [str(it.get("media_id")) for it in items if it.get("media_id")]
    assets = MediaAsset.objects.filter(id__in=ids, deleted_at__isnull=True)
    asset_map = {str(a.id): a for a in assets if a.file}

    # Group by room_category (null -> "unclassified"), preserve sort_order within group
    category_order = [c[0] for c in ROOM_CATEGORIES]
    by_category = {}
    for it in items:
        mid = it.get("media_id")
        if not mid:
            continue
        asset = asset_map.get(str(mid))
        if not asset or not asset.file:
            continue
        url = _resolve_image_url_for_asset(asset, request)
        if not url:
            continue
        cat = it.get("room_category") or "unclassified"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append((it.get("sort_order", 0), url))
    for cat in by_category:
        by_category[cat].sort(key=lambda x: x[0])
        by_category[cat] = [url for _, url in by_category[cat]]

    result = []
    for cat in category_order:
        if cat in by_category and by_category[cat]:
            result.append({
                "room_category": cat,
                "label": ROOM_CATEGORY_LABELS.get(cat, cat),
                "images": by_category[cat],
            })
    if "unclassified" in by_category and by_category["unclassified"]:
        result.append({
            "room_category": "unclassified",
            "label": "Sin clasificar",
            "images": by_category["unclassified"],
        })
    # Lugares personalizados (no predefinidos): orden por primera aparición
    custom_cats = [c for c in by_category if c not in category_order and c != "unclassified"]
    for cat in sorted(custom_cats):
        if by_category[cat]:
            result.append({
                "room_category": cat,
                "label": cat,
                "images": by_category[cat],
            })
    return result


def _accommodation_to_public_dict(acc, request=None, include_photo_tour=False):
    """Mapea Accommodation al formato que espera el frontend (Accommodation type)."""
    images = _resolve_images(acc, request)
    lat = float(acc.latitude) if acc.latitude is not None else 0
    lng = float(acc.longitude) if acc.longitude is not None else 0
    out = {
        "id": str(acc.id),
        "title": acc.title,
        "description": acc.description or "",
        "short_description": acc.short_description or "",
        "price": float(acc.price or 0),
        "rating": float(acc.rating_avg or 0),
        "reviews": acc.review_count or 0,
        "location": {
            "name": acc.location_name or acc.city or acc.country or "",
            "coordinates": {"lat": lat, "lng": lng},
            "address": acc.location_address or None,
        },
        "images": images,
        "amenities": list(acc.amenities or []),
        "propertyType": acc.property_type or "other",
        "bedrooms": acc.bedrooms,
        "beds": acc.beds,
        "bathrooms": acc.bathrooms,
        "guests": acc.guests,
        "country": acc.country or "Chile",
        "city": acc.city or "",
    }
    if include_photo_tour:
        out["photo_tour"] = _build_photo_tour(acc, request)
    return out


def _apply_hotel_inheritance_to_public_dict(data, acc):
    """Apply hotel location/amenities inheritance to an already-built public dict (in place)."""
    hotel = getattr(acc, "hotel", None)
    if not hotel:
        return
    if getattr(acc, "inherit_location_from_hotel", True) and hotel:
        # Use hotel location when room has no own location
        room_has_location = (
            (acc.location_name or "").strip()
            or (acc.location_address or "").strip()
            or (acc.city or "").strip()
            or (acc.country or "").strip()
        )
        if not room_has_location:
            lat = float(hotel.latitude) if hotel.latitude is not None else 0
            lng = float(hotel.longitude) if hotel.longitude is not None else 0
            data["location"] = {
                "name": hotel.location_name or hotel.city or hotel.country or "",
                "coordinates": {"lat": lat, "lng": lng},
                "address": hotel.location_address or None,
            }
            data["country"] = hotel.country or "Chile"
            data["city"] = hotel.city or ""
    if getattr(acc, "inherit_amenities_from_hotel", True) and hotel and (hotel.amenities or []):
        hotel_amenities = list(hotel.amenities or [])
        room_amenities = list(acc.amenities or [])
        data["amenities"] = list(dict.fromkeys(hotel_amenities + room_amenities))


def resolve_room_public_payload(acc, request=None, include_photo_tour=False):
    """
    Build public accommodation dict and apply hotel inheritance (location, amenities).
    Use for hotel rooms list and for accommodation detail when acc has hotel_id.
    """
    data = _accommodation_to_public_dict(acc, request, include_photo_tour=include_photo_tour)
    _apply_hotel_inheritance_to_public_dict(data, acc)
    return data


class PublicAccommodationListSerializer(serializers.BaseSerializer):
    """Serializa lista pública para que el frontend reciba el tipo Accommodation."""

    def to_representation(self, instance):
        request = self.context.get("request")
        return _accommodation_to_public_dict(instance, request)


class PublicAccommodationDetailSerializer(serializers.BaseSerializer):
    """Detalle público: mismo shape que lista + reviews opcional. Imágenes desde media con request. Incluye photo_tour si hay gallery_items con categorías."""

    def to_representation(self, instance):
        request = self.context.get("request")
        data = _accommodation_to_public_dict(instance, request, include_photo_tour=True)
        reviews_qs = instance.reviews.all()[:50]
        data["reviewsList"] = [
            {
                "id": r.id,
                "author_name": r.author_name,
                "author_location": r.author_location or "",
                "rating": r.rating,
                "text": r.text,
                "review_date": r.review_date.isoformat() if r.review_date else None,
                "stay_type": r.stay_type or "",
                "host_reply": r.host_reply or "",
            }
            for r in reviews_qs
        ]
        data["short_description"] = instance.short_description or ""
        data["not_amenities"] = list(instance.not_amenities or [])
        return data
