"""
SuperAdmin Accommodations API.
List, detail with gallery_items + image_url, PATCH for full edit, POST to create.
Create-from-JSON: POST create-from-json/ with accommodation_data (organizer_id optional).
Bulk gallery ZIP: POST bulk-upload-gallery-zip/ with multipart file "zip" (folders = accommodation identifier).
Optional form field "tags" (JSON array of strings) to apply to all uploaded assets in the media library.
"""

import io
import json
import logging
import re
import uuid
import zipfile

from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils.text import slugify
from decimal import Decimal, ROUND_HALF_UP
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.accommodations.models import (
    Accommodation,
    AccommodationBlockedDate,
    AccommodationExtraCharge,
    AccommodationReview,
    Hotel,
)
from apps.accommodations.constants import ROOM_CATEGORIES
from apps.accommodations.public_code_service import ensure_public_code_on_publish
from apps.accommodations.serializers import _normalize_media_url
from apps.media.models import MediaAsset
from apps.organizers.models import Organizer

from ..permissions import IsSuperUser
from ..serializers import JsonAccommodationCreateSerializer

logger = logging.getLogger(__name__)

# room_category: permite valores predefinidos, "unclassified", O cualquier string (lugares personalizados)
PREDEFINED_ROOM_CATEGORIES = {c[0] for c in ROOM_CATEGORIES}


def _optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def _bathrooms_from_validated(validated):
    """
    Resolve (full_bathrooms, half_bathrooms) from validated data.
    Prefers full_bathrooms/half_bathrooms. Legacy: bathrooms (int → all full; float 4.5 → 4 full + 1 half).
    """
    if "full_bathrooms" in validated or "half_bathrooms" in validated:
        full = max(0, int(validated.get("full_bathrooms", 1)))
        half = max(0, int(validated.get("half_bathrooms", 0)))
        return full, half
    b = validated.get("bathrooms", 1)
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
    # e.g. 4.5 → 4 full, 1 half (industry convention)
    full = int(b)
    half = 1
    return max(0, full), max(0, half)


def _parse_review_date(value):
    """Convierte string 'YYYY-MM-DD' en date o None."""
    if value is None:
        return None
    if hasattr(value, "year"):
        return value
    s = (value or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            from datetime import date
            return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
        except (ValueError, TypeError):
            pass
    return None


def _save_accommodation_reviews(acc, reviews_list):
    """
    Crea AccommodationReview para cada ítem en reviews_list (máx 50).
    Acepta text o body, author_name obligatorio. Actualiza acc.rating_avg y acc.review_count.
    """
    if not reviews_list or not isinstance(reviews_list, list):
        return
    created = 0
    for r in reviews_list[:50]:
        if not isinstance(r, dict):
            continue
        author_name = (r.get("author_name") or r.get("author") or "").strip()[:255]
        if not author_name:
            continue
        author_location = (r.get("author_location") or "")[:255]
        rating = max(1, min(5, int(r.get("rating") or 5)))
        text = (r.get("text") or r.get("body") or "")[:5000]
        review_date = _parse_review_date(r.get("review_date"))
        stay_type = (r.get("stay_type") or "")[:100]
        host_reply = (r.get("host_reply") or "")[:2000]
        AccommodationReview.objects.create(
            accommodation=acc,
            author_name=author_name,
            author_location=author_location,
            rating=rating,
            text=text,
            review_date=review_date,
            stay_type=stay_type,
            host_reply=host_reply,
        )
        created += 1
    if created:
        from django.db.models import Avg, Count
        agg = AccommodationReview.objects.filter(accommodation=acc).aggregate(
            avg_rating=Avg("rating"), cnt=Count("id")
        )
        acc.rating_avg = Decimal(str(round(float(agg["avg_rating"] or 0), 1))) if agg["avg_rating"] is not None else None
        acc.review_count = agg["cnt"] or 0
        acc.save(update_fields=["rating_avg", "review_count"])


def _build_gallery_items_with_urls(acc, request=None):
    """
    Return gallery_items with image_url and is_principal for each.
    If gallery_items empty but gallery_media_ids present, build items from gallery_media_ids.
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
    assets = MediaAsset.objects.filter(
        id__in=ids,
        deleted_at__isnull=True,
    )
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


class SuperAdminAccommodationListView(APIView):
    """
    GET /api/v1/superadmin/accommodations/
    List accommodations (superuser only). Query: organizer_id, status, search, type (hotel|rental_hub|independent), ordering, exclude_rooms.
    """
    permission_classes = [IsSuperUser]

    def get(self, request):
        qs = Accommodation.objects.filter(deleted_at__isnull=True).select_related("organizer", "rental_hub", "hotel")

        organizer_id = request.query_params.get("organizer_id")
        if organizer_id:
            qs = qs.filter(organizer_id=organizer_id)
        rental_hub_id = request.query_params.get("rental_hub_id", "").strip()
        rental_hub_slug = request.query_params.get("rental_hub_slug", "").strip()
        if rental_hub_id:
            qs = qs.filter(rental_hub_id=rental_hub_id)
        elif rental_hub_slug:
            qs = qs.filter(rental_hub__slug=rental_hub_slug)
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(slug__icontains=search)
                | Q(city__icontains=search)
                | Q(country__icontains=search)
            )
        # Filtro por tipo: hotel | rental_hub | independent. Si no se envía, usar exclude_rooms.
        type_filter = (request.query_params.get("type") or "").strip().lower()
        if type_filter == "hotel":
            qs = qs.filter(hotel_id__isnull=False)
        elif type_filter == "rental_hub":
            qs = qs.filter(rental_hub_id__isnull=False)
        elif type_filter == "independent":
            qs = qs.filter(hotel_id__isnull=True, rental_hub_id__isnull=True)
        else:
            exclude_rooms = request.query_params.get("exclude_rooms", "true").lower() in ("1", "true", "yes")
            if exclude_rooms:
                qs = qs.filter(hotel_id__isnull=True)

        ordering_param = (request.query_params.get("ordering") or "-created_at").strip()
        allowed_ordering = {
            "title", "-title", "city", "-city", "country", "-country",
            "price", "-price", "guests", "-guests", "status", "-status",
            "created_at", "-created_at",
            "display_order", "-display_order",
        }
        if ordering_param in allowed_ordering:
            qs = qs.order_by(ordering_param)
        else:
            qs = qs.order_by("-created_at")
        # Optional limit so one request doesn't return 100k rows (default: no limit for Super Admin)
        try:
            page_size = int(request.query_params.get("page_size", 0) or 0)
        except (ValueError, TypeError):
            page_size = 0
        if page_size > 0:
            qs = qs[: min(page_size, 50000)]
        results = []
        for acc in qs:
            gallery_ids = acc.gallery_media_ids or []
            if acc.gallery_items:
                ordered = sorted(acc.gallery_items, key=lambda x: x.get("sort_order", 0))
                gallery_ids = [str(it.get("media_id")) for it in ordered if it.get("media_id")]
            item = {
                "id": str(acc.id),
                "title": acc.title,
                "slug": acc.slug,
                "public_code": acc.public_code or None,
                "public_code_prefix": acc.public_code_prefix or None,
                "display_order": acc.display_order,
                "status": acc.status,
                "organizer_id": str(acc.organizer_id) if acc.organizer_id else None,
                "organizer_name": acc.organizer.name if acc.organizer else None,
                "city": acc.city or "",
                "country": acc.country or "",
                "guests": acc.guests,
                "price": float(acc.price or 0),
                "currency": acc.currency or "CLP",
                "photo_count": len(gallery_ids),
            }
            if acc.rental_hub_id:
                item["rental_hub_id"] = str(acc.rental_hub_id)
                item["rental_hub_slug"] = acc.rental_hub.slug if acc.rental_hub else None
            if acc.hotel_id:
                item["hotel_id"] = str(acc.hotel_id)
                item["hotel_slug"] = acc.hotel.slug if acc.hotel else None
            if acc.unit_type or acc.tower or acc.unit_number is not None or acc.floor is not None or acc.square_meters is not None:
                item["unit_type"] = acc.unit_type or ""
                item["tower"] = acc.tower or ""
                item["floor"] = acc.floor
                item["unit_number"] = acc.unit_number or ""
                item["square_meters"] = float(acc.square_meters) if acc.square_meters is not None else None
            results.append(item)
        return Response({"results": results, "count": len(results)})

    def post(self, request):
        """Create accommodation (superuser only). Body: organizer_id (optional if rental_hub_id), title, slug (optional), status, rental_hub_id, unit_type, tower, floor, unit_number, square_meters, ..."""
        data = request.data or {}
        organizer_id = data.get("organizer_id")
        rental_hub_id = data.get("rental_hub_id")
        hotel_id = data.get("hotel_id")
        title = (data.get("title") or "").strip()
        if not title:
            return Response({"detail": "title es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        organizer = None
        if organizer_id:
            try:
                organizer = Organizer.objects.get(id=organizer_id)
            except (Organizer.DoesNotExist, ValueError):
                return Response({"detail": "Organizador no encontrado."}, status=status.HTTP_400_BAD_REQUEST)
        elif not rental_hub_id and not hotel_id:
            return Response({"detail": "organizer_id, rental_hub_id o hotel_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        rental_hub = None
        if rental_hub_id:
            from apps.accommodations.models import RentalHub
            try:
                rental_hub = RentalHub.objects.get(id=rental_hub_id)
            except (RentalHub.DoesNotExist, ValueError):
                return Response({"detail": "Central de arrendamiento no encontrada."}, status=status.HTTP_400_BAD_REQUEST)

        hotel = None
        if hotel_id:
            try:
                hotel = Hotel.objects.get(id=hotel_id)
            except (Hotel.DoesNotExist, ValueError):
                return Response({"detail": "Hotel no encontrado."}, status=status.HTTP_400_BAD_REQUEST)

        slug_raw = (data.get("slug") or "").strip()
        slug = slugify(title) if not slug_raw else slugify(slug_raw)
        if not slug:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "alojamiento"
        if Accommodation.objects.filter(slug=slug, deleted_at__isnull=True).exists():
            return Response({"detail": f"Ya existe un alojamiento con slug '{slug}'."}, status=status.HTTP_400_BAD_REQUEST)

        status_val = data.get("status", "draft")
        if status_val not in ("draft", "published", "cancelled"):
            status_val = "draft"
        property_type = data.get("property_type", "cabin")
        if property_type not in dict(Accommodation.PROPERTY_TYPE_CHOICES):
            property_type = "cabin"

        payment_model = (data.get("payment_model") or "").strip()
        if payment_model not in ("", "full_platform", "commission_only"):
            payment_model = ""
        tuki_commission_rate = None
        if data.get("tuki_commission_rate") is not None and data.get("tuki_commission_rate") != "":
            try:
                r = Decimal(str(data["tuki_commission_rate"]))
                if Decimal("0") <= r <= Decimal("1"):
                    tuki_commission_rate = r
            except (TypeError, ValueError):
                pass

        acc = Accommodation(
            title=title,
            slug=slug,
            organizer=organizer,
            rental_hub=rental_hub,
            hotel=hotel,
            status=status_val,
            property_type=property_type,
            description=(data.get("description") or "").strip(),
            short_description=(data.get("short_description") or "").strip()[:500],
            location_name=(data.get("location_name") or "").strip()[:255],
            location_address=(data.get("location_address") or "").strip(),
            country=(data.get("country") or "Chile").strip()[:255],
            city=(data.get("city") or "").strip()[:255],
            guests=max(1, int(data.get("guests", 2))),
            bedrooms=max(0, int(data.get("bedrooms", 1))),
            full_bathrooms=_bathrooms_from_validated(data)[0],
            half_bathrooms=_bathrooms_from_validated(data)[1],
            beds=max(0, int(data.get("beds", 1))) if data.get("beds") is not None else 1,
            price=Decimal(str(data.get("price", 0))) if data.get("price") is not None else Decimal("0"),
            currency=(data.get("currency") or "CLP")[:3],
            amenities=[str(x) for x in (data.get("amenities") if isinstance(data.get("amenities"), list) else []) if x],
            not_amenities=[str(x) for x in (data.get("not_amenities") if isinstance(data.get("not_amenities"), list) else []) if x],
            unit_type=(data.get("unit_type") or "").strip()[:30],
            tower=(data.get("tower") or "").strip()[:30],
            floor=_optional_int(data.get("floor")),
            unit_number=(data.get("unit_number") or "").strip()[:20],
            square_meters=_optional_decimal(data.get("square_meters")),
            inherit_location_from_hotel=data.get("inherit_location_from_hotel", True),
            inherit_amenities_from_hotel=data.get("inherit_amenities_from_hotel", True),
            room_type_code=(data.get("room_type_code") or "").strip()[:30],
            external_id=(data.get("external_id") or "").strip()[:255],
            min_nights=_optional_int(data.get("min_nights")) if data.get("min_nights") is not None else None,
            payment_model=payment_model,
            tuki_commission_rate=tuki_commission_rate,
        )
        if data.get("latitude") is not None:
            try:
                acc.latitude = Decimal(str(data["latitude"]))
            except (TypeError, ValueError):
                pass
        if data.get("longitude") is not None:
            try:
                acc.longitude = Decimal(str(data["longitude"]))
            except (TypeError, ValueError):
                pass
        acc.save()

        # Galería opcional al crear: gallery_media_ids o gallery_items
        gallery_input = data.get("gallery_items") if isinstance(data.get("gallery_items"), list) else None
        if gallery_input:
            media_ids = []
            for i, it in enumerate(gallery_input):
                if not isinstance(it, dict):
                    continue
                mid = it.get("media_id")
                if not mid:
                    continue
                try:
                    mid_str = str(uuid.UUID(str(mid)))
                except (ValueError, TypeError):
                    continue
                media_ids.append((mid_str, it.get("room_category"), it.get("sort_order", i), it.get("is_principal", False)))
            if media_ids:
                all_mids = [m[0] for m in media_ids]
                assets = MediaAsset.objects.filter(id__in=all_mids, deleted_at__isnull=True)
                found = {str(a.id) for a in assets}
                ordered = sorted(
                    [{"media_id": m[0], "room_category": m[1], "sort_order": m[2], "is_principal": m[3]} for m in media_ids if m[0] in found],
                    key=lambda x: x["sort_order"],
                )
                if ordered:
                    acc.gallery_items = ordered
                    acc.gallery_media_ids = [it["media_id"] for it in ordered]
                    acc.images = []
                    acc.save(update_fields=["gallery_items", "gallery_media_ids", "images"])
        else:
            ids_raw = data.get("gallery_media_ids")
            if isinstance(ids_raw, list) and ids_raw:
                valid_ids = []
                for mid in ids_raw:
                    try:
                        valid_ids.append(str(uuid.UUID(str(mid))))
                    except (ValueError, TypeError):
                        continue
                if valid_ids:
                    assets = MediaAsset.objects.filter(id__in=valid_ids, deleted_at__isnull=True)
                    found = {str(a.id) for a in assets}
                    valid_ids = [i for i in valid_ids if i in found]
                    if valid_ids:
                        acc.gallery_items = [{"media_id": i, "room_category": None, "sort_order": idx, "is_principal": idx == 0} for idx, i in enumerate(valid_ids)]
                        acc.gallery_media_ids = valid_ids
                        acc.images = []
                        acc.save(update_fields=["gallery_items", "gallery_media_ids", "images"])

        # Return same shape as GET detail
        gallery_items = _build_gallery_items_with_urls(acc, request)
        predefined = [{"value": c[0], "label": c[1]} for c in ROOM_CATEGORIES]
        custom = []
        room_categories = predefined + [{"value": "unclassified", "label": "Sin clasificar"}] + custom
        create_payload = {
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
            "amenities": acc.amenities or [],
            "not_amenities": acc.not_amenities or [],
            "photo_count": len(gallery_items),
            "gallery_items": gallery_items,
            "room_categories": room_categories,
            "min_nights": acc.min_nights,
            "payment_model": acc.payment_model or "",
            "tuki_commission_rate": float(acc.tuki_commission_rate) if acc.tuki_commission_rate is not None else None,
        }
        if acc.rental_hub_id:
            create_payload["rental_hub_id"] = str(acc.rental_hub_id)
            create_payload["rental_hub_slug"] = acc.rental_hub.slug if acc.rental_hub else None
        if acc.hotel_id:
            create_payload["hotel_id"] = str(acc.hotel_id)
            create_payload["hotel_slug"] = acc.hotel.slug if acc.hotel else None
            create_payload["inherit_location_from_hotel"] = acc.inherit_location_from_hotel
            create_payload["inherit_amenities_from_hotel"] = acc.inherit_amenities_from_hotel
            create_payload["room_type_code"] = acc.room_type_code or ""
        create_payload["external_id"] = acc.external_id or ""
        create_payload["unit_type"] = acc.unit_type or ""
        create_payload["tower"] = acc.tower or ""
        create_payload["floor"] = acc.floor
        create_payload["unit_number"] = acc.unit_number or ""
        create_payload["square_meters"] = float(acc.square_meters) if acc.square_meters is not None else None
        return Response(create_payload, status=status.HTTP_201_CREATED)


class SuperAdminAccommodationDetailView(APIView):
    """
    GET /api/v1/superadmin/accommodations/<uuid>/
    PATCH /api/v1/superadmin/accommodations/<uuid>/
    Detail for editing: full accommodation + gallery_items.
    PATCH allows updating country, city, title, etc.
    """
    permission_classes = [IsSuperUser]

    def _get_accommodation(self, accommodation_id):
        return Accommodation.objects.filter(
            id=accommodation_id,
            deleted_at__isnull=True,
        ).select_related("organizer", "rental_hub", "hotel").get()

    def get(self, request, accommodation_id):
        try:
            acc = self._get_accommodation(accommodation_id)
        except (Accommodation.DoesNotExist, ValueError):
            return Response({"detail": "Alojamiento no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        gallery_items = _build_gallery_items_with_urls(acc, request)
        # Incluir categorías predefinidas + las personalizadas que ya existen en gallery_items
        predefined = [{"value": c[0], "label": c[1]} for c in ROOM_CATEGORIES]
        custom = [
            {"value": v, "label": v}
            for v in sorted(
                {it.get("room_category") for it in (acc.gallery_items or []) if it.get("room_category")}
                - PREDEFINED_ROOM_CATEGORIES
                - {"unclassified"}
            )
        ]
        room_categories = predefined + [{"value": "unclassified", "label": "Sin clasificar"}] + custom

        payload = {
            "id": str(acc.id),
            "title": acc.title,
            "slug": acc.slug,
            "public_code": acc.public_code or None,
            "public_code_prefix": acc.public_code_prefix or None,
            "display_order": acc.display_order,
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
        payload["payment_model"] = acc.payment_model or ""
        payload["tuki_commission_rate"] = float(acc.tuki_commission_rate) if acc.tuki_commission_rate is not None else None
        # Extra charges (cobros adicionales v1.5)
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
        return Response(payload)

    def patch(self, request, accommodation_id):
        """Update accommodation fields (all editable except slug)."""
        try:
            acc = self._get_accommodation(accommodation_id)
        except (Accommodation.DoesNotExist, ValueError):
            return Response({"detail": "Alojamiento no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        update_fields = []

        # Text fields
        for field in ("title", "description", "short_description", "country", "city", "location_name", "location_address"):
            if field in data:
                val = data[field]
                setattr(acc, field, str(val).strip() if val is not None else "")
                update_fields.append(field)

        # Status
        if "status" in data and data["status"] in ("draft", "published", "cancelled"):
            acc.status = data["status"]
            update_fields.append("status")

        # Property type
        if "property_type" in data and data["property_type"] in dict(Accommodation.PROPERTY_TYPE_CHOICES):
            acc.property_type = data["property_type"]
            update_fields.append("property_type")

        # Numeric capacity (bathrooms: full_bathrooms + half_bathrooms)
        for field in ("guests", "bedrooms", "beds"):
            if field in data:
                try:
                    n = int(data[field])
                    if field == "guests" and n < 1:
                        n = 1
                    elif n < 0:
                        n = 0
                    setattr(acc, field, n)
                    update_fields.append(field)
                except (TypeError, ValueError):
                    pass
        if "full_bathrooms" in data:
            try:
                acc.full_bathrooms = max(0, int(data["full_bathrooms"]))
                update_fields.append("full_bathrooms")
            except (TypeError, ValueError):
                pass
        if "half_bathrooms" in data:
            try:
                acc.half_bathrooms = max(0, int(data["half_bathrooms"]))
                update_fields.append("half_bathrooms")
            except (TypeError, ValueError):
                pass
        # Legacy: "bathrooms" → all full
        if "bathrooms" in data and "full_bathrooms" not in data and "half_bathrooms" not in data:
            try:
                acc.full_bathrooms = max(0, int(data["bathrooms"]))
                acc.half_bathrooms = 0
                update_fields.extend(["full_bathrooms", "half_bathrooms"])
            except (TypeError, ValueError):
                pass

        # Price: quantize to 2 decimals to avoid float artifacts (e.g. 160000 → 160002)
        if "price" in data:
            try:
                raw = Decimal(str(data["price"]))
                if raw < 0:
                    raw = Decimal("0")
                acc.price = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                update_fields.append("price")
            except (TypeError, ValueError):
                pass
        if "currency" in data and data["currency"]:
            acc.currency = str(data["currency"])[:3]
            update_fields.append("currency")

        # Lat/lng
        for field in ("latitude", "longitude"):
            if field in data:
                if data[field] is None:
                    setattr(acc, field, None)
                else:
                    try:
                        setattr(acc, field, Decimal(str(data[field])))
                    except (TypeError, ValueError):
                        pass
                update_fields.append(field)

        # JSON list fields
        if "amenities" in data and isinstance(data["amenities"], list):
            acc.amenities = [str(x) for x in data["amenities"] if x]
            update_fields.append("amenities")
        if "not_amenities" in data and isinstance(data["not_amenities"], list):
            acc.not_amenities = [str(x) for x in data["not_amenities"] if x]
            update_fields.append("not_amenities")

        # Rental hub / unit fields
        if "unit_type" in data:
            acc.unit_type = (data["unit_type"] or "").strip()[:30]
            update_fields.append("unit_type")
        if "tower" in data:
            acc.tower = (data["tower"] or "").strip()[:30]
            update_fields.append("tower")
        if "floor" in data:
            acc.floor = _optional_int(data["floor"])
            update_fields.append("floor")
        if "unit_number" in data:
            acc.unit_number = (data["unit_number"] or "").strip()[:20]
            update_fields.append("unit_number")
        if "square_meters" in data:
            acc.square_meters = _optional_decimal(data["square_meters"])
            update_fields.append("square_meters")

        # Central de arrendamiento (rental hub)
        if "rental_hub_id" in data:
            rid = data["rental_hub_id"]
            if rid is None or rid == "":
                acc.rental_hub = None
            else:
                from apps.accommodations.models import RentalHub
                try:
                    acc.rental_hub = RentalHub.objects.get(id=rid)
                except (RentalHub.DoesNotExist, ValueError):
                    return Response(
                        {"detail": "Central de arrendamiento no encontrada."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            update_fields.append("rental_hub_id")

        # Hotel / room fields
        if "hotel_id" in data:
            hid = data["hotel_id"]
            if hid:
                try:
                    acc.hotel = Hotel.objects.get(id=hid)
                except (Hotel.DoesNotExist, ValueError):
                    return Response({"detail": "Hotel no encontrado."}, status=status.HTTP_400_BAD_REQUEST)
            else:
                acc.hotel = None
            update_fields.append("hotel_id")
        if "inherit_location_from_hotel" in data:
            acc.inherit_location_from_hotel = bool(data["inherit_location_from_hotel"])
            update_fields.append("inherit_location_from_hotel")
        if "inherit_amenities_from_hotel" in data:
            acc.inherit_amenities_from_hotel = bool(data["inherit_amenities_from_hotel"])
            update_fields.append("inherit_amenities_from_hotel")
        if "room_type_code" in data:
            acc.room_type_code = (data["room_type_code"] or "").strip()[:30]
            update_fields.append("room_type_code")
        if "external_id" in data:
            acc.external_id = (data["external_id"] or "").strip()[:255]
            update_fields.append("external_id")
        if "min_nights" in data:
            acc.min_nights = _optional_int(data["min_nights"])
            update_fields.append("min_nights")

        # Número de orden (opcional; el código público se genera al publicar)
        if "display_order" in data:
            vo = _optional_int(data["display_order"])
            if vo is not None and vo >= 1:
                prefix = (data.get("public_code_prefix") or acc.public_code_prefix or "").strip()[:30]
                if prefix:
                    would_be_code = f"{prefix}-{vo:03d}"
                    if Accommodation.objects.filter(public_code=would_be_code).exclude(pk=acc.pk).exists():
                        return Response(
                            {"detail": f"El código que se generaría ({would_be_code}) ya existe en otro alojamiento. Usa otro número de orden o prefijo."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                acc.display_order = vo
                update_fields.append("display_order")
        # Prefijo del código público (ej. Tuki-PV → Tuki-PV-001)
        if "public_code_prefix" in data:
            val = (data.get("public_code_prefix") or "").strip()[:30]
            if val:
                # El código que se generaría al publicar es {prefix}-{display_order:03d}; no puede existir en otro
                order = acc.display_order if (acc.display_order is not None and acc.display_order >= 1) else 1
                would_be_code = f"{val}-{order:03d}"
                if Accommodation.objects.filter(public_code=would_be_code).exclude(pk=acc.pk).exists():
                    return Response(
                        {"detail": f"El código que se generaría ({would_be_code}) ya existe en otro alojamiento. Usa otro prefijo o cambia el número de orden."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            acc.public_code_prefix = val or ""
            update_fields.append("public_code_prefix")

        # Al publicar: generar public_code y display_order si no existen
        if acc.status == "published":
            for f in ensure_public_code_on_publish(acc):
                if f not in update_fields:
                    update_fields.append(f)

        # Modelo de pago y comisión
        if "payment_model" in data:
            val = (data["payment_model"] or "").strip()
            if val in ("", "full_platform", "commission_only"):
                acc.payment_model = val
                update_fields.append("payment_model")
        if "tuki_commission_rate" in data:
            v = data["tuki_commission_rate"]
            if v is None or v == "":
                acc.tuki_commission_rate = None
                update_fields.append("tuki_commission_rate")
            else:
                try:
                    rate = Decimal(str(v))
                    if Decimal("0") <= rate <= Decimal("1"):
                        acc.tuki_commission_rate = rate
                        update_fields.append("tuki_commission_rate")
                except (TypeError, ValueError):
                    pass

        if update_fields:
            acc.save(update_fields=update_fields)

        # Extra charges (cobros adicionales v1.5): full list sync
        if "extra_charges" in data and isinstance(data["extra_charges"], list):
            kept_ids = []
            for idx, item in enumerate(data["extra_charges"]):
                if not isinstance(item, dict):
                    continue
                code = (item.get("code") or "").strip()[:64]
                if not code:
                    continue
                name = (item.get("name") or "").strip()[:255]
                charge_type = (item.get("charge_type") or "per_stay")[:20]
                if charge_type not in ("per_stay", "per_night"):
                    charge_type = "per_stay"
                try:
                    amount = Decimal(str(item.get("amount") or 0))
                    if amount < 0:
                        amount = Decimal("0")
                except (TypeError, ValueError):
                    amount = Decimal("0")
                currency = (item.get("currency") or "").strip()[:3] or None
                is_optional = bool(item.get("is_optional", True))
                default_quantity = max(1, int(item.get("default_quantity") or 1))
                max_quantity = _optional_int(item.get("max_quantity"))
                is_active = bool(item.get("is_active", True))
                display_order = max(0, int(item.get("display_order") or idx))
                description = (item.get("description") or "")[:5000]

                extra_id = item.get("id")
                if extra_id:
                    try:
                        extra = AccommodationExtraCharge.objects.get(
                            id=extra_id,
                            accommodation=acc,
                        )
                        extra.name = name
                        extra.charge_type = charge_type
                        extra.amount = amount
                        extra.currency = currency
                        extra.is_optional = is_optional
                        extra.default_quantity = default_quantity
                        extra.max_quantity = max_quantity
                        extra.is_active = is_active
                        extra.display_order = display_order
                        extra.description = description
                        extra.save()
                        kept_ids.append(extra.id)
                        continue
                    except (AccommodationExtraCharge.DoesNotExist, ValueError):
                        pass
                # Create new (code must be unique per accommodation)
                extra, _ = AccommodationExtraCharge.objects.update_or_create(
                    accommodation=acc,
                    code=code,
                    defaults={
                        "name": name,
                        "description": description,
                        "charge_type": charge_type,
                        "amount": amount,
                        "currency": currency,
                        "is_optional": is_optional,
                        "default_quantity": default_quantity,
                        "max_quantity": max_quantity,
                        "is_active": is_active,
                        "display_order": display_order,
                    },
                )
                kept_ids.append(extra.id)
            # Remove extras not in the submitted list
            acc.extra_charges.exclude(id__in=kept_ids).delete()

        return self.get(request, accommodation_id)


class SuperAdminAccommodationGalleryUpdateView(APIView):
    """
    PATCH /api/v1/superadmin/accommodations/<uuid>/gallery/
    Body: { "gallery_items": [ { "media_id": "uuid", "room_category": "sala"|...|null, "sort_order": 0 } ] }
    Updates gallery_items and syncs gallery_media_ids. Validates media belong to accommodation's organizer or global.
    """
    permission_classes = [IsSuperUser]

    def patch(self, request, accommodation_id):
        try:
            acc = Accommodation.objects.filter(
                id=accommodation_id,
                deleted_at__isnull=True,
            ).select_related("organizer").get()
        except (Accommodation.DoesNotExist, ValueError):
            return Response({"detail": "Alojamiento no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        items = data.get("gallery_items")
        if items is None:
            return Response({"detail": "gallery_items es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(items, list):
            return Response({"detail": "gallery_items debe ser una lista."}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize and validate (room_category: predefined, "unclassified", or any custom string)
        normalized = []
        media_ids = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            mid = it.get("media_id")
            if not mid:
                continue
            try:
                mid_str = str(uuid.UUID(str(mid)))
            except (ValueError, TypeError):
                return Response(
                    {"detail": f"media_id inválido: {mid}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            room_category = it.get("room_category")
            if room_category is not None and not isinstance(room_category, str):
                room_category = str(room_category) if room_category else None
            if room_category is not None and room_category.strip() == "":
                room_category = None
            # Allow predefined, "unclassified", or any custom string for places
            if room_category is not None and room_category not in PREDEFINED_ROOM_CATEGORIES and room_category != "unclassified":
                # Custom places allowed (e.g. "Nuevo lugar", "Terraza")
                pass
            sort_order = it.get("sort_order", i)
            if not isinstance(sort_order, int):
                try:
                    sort_order = int(sort_order)
                except (TypeError, ValueError):
                    sort_order = i
            is_principal = it.get("is_principal", False)
            if not isinstance(is_principal, bool):
                is_principal = bool(is_principal)
            normalized.append({
                "media_id": mid_str,
                "room_category": room_category,
                "sort_order": sort_order,
                "is_principal": is_principal,
            })
            media_ids.append(mid_str)

        # Validate all MediaAssets exist and belong to accommodation's organizer or are global (skip when clearing gallery)
        if media_ids:
            assets = MediaAsset.objects.filter(id__in=media_ids, deleted_at__isnull=True)
            found_ids = {str(a.id) for a in assets}
            for mid in media_ids:
                if mid not in found_ids:
                    return Response(
                        {"detail": f"MediaAsset no encontrado o eliminado: {mid}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            acc_organizer_id = str(acc.organizer_id) if acc.organizer_id else None
            for a in assets:
                if a.scope == "organizer" and str(a.organizer_id) != acc_organizer_id:
                    return Response(
                        {"detail": f"El asset {a.id} no pertenece al organizador de este alojamiento."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Save: gallery_items and sync gallery_media_ids (order by sort_order).
        # Siempre vaciar acc.images (legacy) para que la API pública solo use gallery_media_ids;
        # si no, las URLs viejas en images siguen apareciendo en la página pública.
        ordered = sorted(normalized, key=lambda x: x["sort_order"])
        acc.gallery_items = ordered
        acc.gallery_media_ids = [it["media_id"] for it in ordered]
        acc.images = []
        update_fields = ["gallery_items", "gallery_media_ids", "images"]
        acc.save(update_fields=update_fields)

        gallery_with_urls = _build_gallery_items_with_urls(acc, request)
        return Response({
            "gallery_items": gallery_with_urls,
            "photo_count": len(gallery_with_urls),
        })


# Bulk ZIP: only image extensions; folder name = accommodation public_code or slug
BULK_ZIP_MAX_SIZE_BYTES = 150 * 1024 * 1024  # 150 MB
BULK_ZIP_MAX_FILES = 500
BULK_ZIP_ALLOWED_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp", "gif"})


def _find_accommodation_by_folder_name(folder_name):
    """Resolve folder name to Accommodation by public_code (case-insensitive) or slug. Returns None if not found."""
    key = (folder_name or "").strip()
    if not key:
        return None
    acc = (
        Accommodation.objects.filter(deleted_at__isnull=True)
        .filter(Q(public_code__iexact=key) | Q(slug__iexact=key))
        .select_related("organizer")
        .first()
    )
    return acc


@api_view(["POST"])
@permission_classes([IsSuperUser])
def bulk_upload_gallery_zip(request):
    """
    POST /api/v1/superadmin/accommodations/bulk-upload-gallery-zip/
    Multipart: file "zip" or "file" = ZIP with top-level folders.
    Folder name = accommodation identifier (public_code e.g. Tuki001, or slug).
    Images inside each folder are uploaded to media library and assigned to that accommodation's gallery.

    Limits: ZIP up to 150 MB, max 500 image files. Returns summary with per-folder results and errors.
    """
    if not request.FILES:
        return Response(
            {"detail": "Envía un archivo ZIP (campo 'zip' o 'file')."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    zip_file = request.FILES.get("zip") or request.FILES.get("file")
    if not zip_file:
        return Response(
            {"detail": "Falta el archivo ZIP. Usa el campo 'zip' o 'file'."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if zip_file.size > BULK_ZIP_MAX_SIZE_BYTES:
        return Response(
            {"detail": f"El ZIP no puede superar {BULK_ZIP_MAX_SIZE_BYTES // (1024*1024)} MB."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        with zipfile.ZipFile(zip_file, "r") as zf:
            namelist = zf.namelist()
    except zipfile.BadZipFile:
        return Response(
            {"detail": "El archivo no es un ZIP válido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Group members by top-level folder: "Tuki001/a.jpg" -> folder "Tuki001"
    by_folder = {}
    for name in namelist:
        if name.startswith("__MACOSX/") or "/." in name or name.endswith("/"):
            continue
        parts = name.replace("\\", "/").strip("/").split("/")
        if not parts:
            continue
        folder = parts[0].strip()
        if not folder:
            continue
        ext = (parts[-1].split(".")[-1] if "." in parts[-1] else "").lower()
        if ext not in BULK_ZIP_ALLOWED_EXTENSIONS:
            continue
        if folder not in by_folder:
            by_folder[folder] = []
        by_folder[folder].append((name, parts[-1]))

    if not by_folder:
        return Response(
            {"detail": "No se encontraron carpetas con imágenes (jpg, jpeg, png, webp, gif). Cada carpeta debe tener el nombre del alojamiento (public_code o slug)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    total_files = sum(len(files) for files in by_folder.values())
    if total_files > BULK_ZIP_MAX_FILES:
        return Response(
            {"detail": f"Máximo {BULK_ZIP_MAX_FILES} imágenes en total. Tienes {total_files}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Optional tags for media library (applied to every uploaded asset)
    tags_list = []
    raw_tags = request.data.get("tags") or request.POST.get("tags")
    if raw_tags:
        if isinstance(raw_tags, list):
            tags_list = [str(t).strip() for t in raw_tags if t and str(t).strip()][:50]
        else:
            try:
                parsed = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
                if isinstance(parsed, list):
                    tags_list = [str(t).strip() for t in parsed if t and str(t).strip()][:50]
            except (json.JSONDecodeError, TypeError):
                pass

    # Re-open zip for reading (file was consumed by namelist)
    zip_file.seek(0)
    results = []
    total_uploaded = 0
    global_errors = []

    try:
        with zipfile.ZipFile(zip_file, "r") as zf:
            for folder_name, file_entries in sorted(by_folder.items()):
                acc = _find_accommodation_by_folder_name(folder_name)
                folder_result = {
                    "folder_name": folder_name,
                    "accommodation_id": str(acc.id) if acc else None,
                    "accommodation_title": acc.title if acc else None,
                    "uploaded": 0,
                    "errors": [],
                    "new_media_ids": [],
                }
                if not acc:
                    folder_result["errors"].append("Alojamiento no encontrado (public_code o slug no coincide)")
                    results.append(folder_result)
                    continue
                if not acc.organizer_id:
                    folder_result["errors"].append(
                        "El alojamiento no tiene organizador; no se pueden subir fotos a la galería."
                    )
                    results.append(folder_result)
                    continue

                existing_items = list(acc.gallery_items or [])
                next_sort = max((it.get("sort_order", i) for i, it in enumerate(existing_items)), default=-1) + 1
                has_principal = any(it.get("is_principal") for it in existing_items)
                new_media_ids = []

                for zip_path, filename in file_entries:
                    try:
                        data = zf.read(zip_path)
                    except Exception as e:
                        folder_result["errors"].append(f"{filename}: no se pudo leer ({e})")
                        continue
                    if len(data) == 0:
                        folder_result["errors"].append(f"{filename}: archivo vacío")
                        continue
                    ext = (filename.split(".")[-1] if "." in filename else "").lower()
                    content_type = f"image/{ext}" if ext in ("jpeg", "jpg", "png", "webp", "gif") else "image/jpeg"
                    if ext == "jpg":
                        content_type = "image/jpeg"

                    asset = MediaAsset(
                        scope="organizer",
                        organizer_id=acc.organizer_id,
                        uploaded_by=request.user,
                        original_filename=filename[:255],
                        content_type=content_type,
                        size_bytes=len(data),
                    )
                    try:
                        asset.file.save(filename, ContentFile(data), save=True)
                        asset.generate_thumbnail()
                        if tags_list:
                            asset.tags = tags_list
                            asset.save(update_fields=["tags"])
                    except Exception as e:
                        logger.warning("Bulk ZIP: failed to save asset %s: %s", filename, e)
                        folder_result["errors"].append(f"{filename}: {e}")
                        continue
                    new_media_ids.append((asset.id, next_sort, not has_principal))
                    next_sort += 1
                    if not has_principal:
                        has_principal = True
                    folder_result["uploaded"] += 1
                    total_uploaded += 1

                for mid, sort_order, is_principal in new_media_ids:
                    existing_items.append({
                        "media_id": str(mid),
                        "room_category": None,
                        "sort_order": sort_order,
                        "is_principal": is_principal,
                    })
                if new_media_ids:
                    ordered = sorted(existing_items, key=lambda x: x.get("sort_order", 0))
                    acc.gallery_items = ordered
                    acc.gallery_media_ids = [it["media_id"] for it in ordered]
                    acc.images = []
                    acc.save(update_fields=["gallery_items", "gallery_media_ids", "images"])
                    folder_result["new_media_ids"] = [str(mid) for mid, _, _ in new_media_ids]

                results.append(folder_result)
    except Exception as e:
        logger.exception("Bulk ZIP processing failed: %s", e)
        global_errors.append(str(e))
        return Response(
            {"detail": "Error al procesar el ZIP.", "errors": global_errors, "results": results},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    accommodations_not_found = [r["folder_name"] for r in results if r["accommodation_id"] is None]
    accommodations_matched = [r for r in results if r["accommodation_id"]]
    return Response({
        "folders_processed": len(results),
        "accommodations_matched": len(accommodations_matched),
        "accommodations_not_found": accommodations_not_found,
        "total_images_uploaded": total_uploaded,
        "results": results,
        "errors": global_errors,
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsSuperUser])
def create_accommodation_from_json(request):
    """
    POST /api/v1/superadmin/accommodations/create-from-json/
    Body: { "accommodation_data": { ... }, "organizer_id": "uuid" (optional) }
    If organizer_id is omitted, accommodation is created with organizer=null (superadmin-owned).
    """
    data = request.data or {}
    accommodation_data = data.get("accommodation_data")
    if not accommodation_data:
        return Response(
            {"detail": "El campo 'accommodation_data' es requerido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = JsonAccommodationCreateSerializer(data=accommodation_data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    validated = serializer.validated_data
    organizer_id = validated.pop("organizer_id", None) or data.get("organizer_id")
    organizer = None
    if organizer_id:
        try:
            organizer = Organizer.objects.get(id=organizer_id)
        except (Organizer.DoesNotExist, ValueError):
            return Response(
                {"detail": "Organizador no encontrado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    title = (validated.get("title") or "").strip()
    if not title:
        return Response({"detail": "title es requerido."}, status=status.HTTP_400_BAD_REQUEST)

    slug_raw = (validated.get("slug") or "").strip()
    slug = slugify(title) if not slug_raw else slugify(slug_raw)
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "alojamiento"
    if Accommodation.objects.filter(slug=slug, deleted_at__isnull=True).exists():
        return Response(
            {"detail": f"Ya existe un alojamiento con slug '{slug}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    status_val = validated.get("status", "draft")
    if status_val not in ("draft", "published", "cancelled"):
        status_val = "draft"
    property_type = validated.get("property_type", "cabin")
    if property_type not in dict(Accommodation.PROPERTY_TYPE_CHOICES):
        property_type = "cabin"

    rental_hub = None
    if validated.get("rental_hub_id"):
        from apps.accommodations.models import RentalHub
        try:
            rental_hub = RentalHub.objects.get(id=validated["rental_hub_id"])
        except (RentalHub.DoesNotExist, ValueError):
            return Response({"detail": "Central de arrendamiento no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
    hotel = None
    if validated.get("hotel_id"):
        try:
            hotel = Hotel.objects.get(id=validated["hotel_id"])
        except (Hotel.DoesNotExist, ValueError):
            return Response({"detail": "Hotel no encontrado."}, status=status.HTTP_400_BAD_REQUEST)

    acc = Accommodation(
        title=title,
        slug=slug,
        organizer=organizer,
        rental_hub=rental_hub,
        hotel=hotel,
        status=status_val,
        property_type=property_type,
        description=(validated.get("description") or "").strip(),
        short_description=(validated.get("short_description") or "").strip()[:500],
        location_name=(validated.get("location_name") or "").strip()[:255],
        location_address=(validated.get("location_address") or "").strip(),
        country=(validated.get("country") or "Chile").strip()[:255],
        city=(validated.get("city") or "").strip()[:255],
        guests=max(1, int(validated.get("guests", 2))),
        bedrooms=max(0, int(validated.get("bedrooms", 1))),
        full_bathrooms=_bathrooms_from_validated(validated)[0],
        half_bathrooms=_bathrooms_from_validated(validated)[1],
        beds=max(0, int(validated.get("beds", 1))) if validated.get("beds") is not None else 1,
        price=Decimal(str(validated.get("price", 0))) if validated.get("price") is not None else Decimal("0"),
        currency=(validated.get("currency") or "CLP")[:3],
        amenities=[str(x) for x in (validated.get("amenities") or []) if x],
        not_amenities=[str(x) for x in (validated.get("not_amenities") or []) if x],
        unit_type=(validated.get("unit_type") or "").strip()[:30],
        tower=(validated.get("tower") or "").strip()[:30],
        floor=_optional_int(validated.get("floor")),
        unit_number=(validated.get("unit_number") or "").strip()[:20],
        square_meters=_optional_decimal(validated.get("square_meters")),
        inherit_location_from_hotel=validated.get("inherit_location_from_hotel", True),
        inherit_amenities_from_hotel=validated.get("inherit_amenities_from_hotel", True),
        room_type_code=(validated.get("room_type_code") or "").strip()[:30],
        external_id=(validated.get("external_id") or "").strip()[:255],
        min_nights=_optional_int(validated.get("min_nights")) if validated.get("min_nights") is not None else None,
    )
    if validated.get("latitude") is not None:
        try:
            acc.latitude = Decimal(str(validated["latitude"]))
        except (TypeError, ValueError):
            pass
    if validated.get("longitude") is not None:
        try:
            acc.longitude = Decimal(str(validated["longitude"]))
        except (TypeError, ValueError):
            pass
    if validated.get("images"):
        acc.images = [str(u) for u in validated["images"] if u][:50]
    if validated.get("gallery_media_ids"):
        acc.gallery_media_ids = [str(u) for u in validated["gallery_media_ids"] if u][:50]

    # display_order y public_code_prefix opcionales desde JSON
    if "display_order" in validated and validated.get("display_order") is not None:
        try:
            do = max(1, int(validated["display_order"]))
            acc.display_order = do
        except (TypeError, ValueError):
            pass
    if "public_code_prefix" in validated:
        acc.public_code_prefix = (validated.get("public_code_prefix") or "").strip()[:30]

    acc.save()

    # Al publicar: generar public_code (y display_order si no se envió)
    if status_val == "published":
        pub_fields = ensure_public_code_on_publish(acc)
        if pub_fields:
            acc.save(update_fields=pub_fields)

    # Cobros adicionales (extra_charges) desde JSON
    extra_charges_data = validated.get("extra_charges")
    if extra_charges_data and isinstance(extra_charges_data, list):
        seen_codes = set()
        for idx, item in enumerate(extra_charges_data):
            if not isinstance(item, dict):
                continue
            code = (item.get("code") or "").strip()[:64]
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            name = (item.get("name") or "").strip()[:255] or code
            charge_type = (item.get("charge_type") or "per_stay")[:20]
            if charge_type not in ("per_stay", "per_night"):
                charge_type = "per_stay"
            try:
                amount = Decimal(str(item.get("amount") or 0))
                if amount < 0:
                    amount = Decimal("0")
            except (TypeError, ValueError):
                amount = Decimal("0")
            currency = (item.get("currency") or "").strip()[:3] or None
            is_optional = bool(item.get("is_optional", True))
            default_quantity = max(1, int(item.get("default_quantity") or 1))
            max_quantity = _optional_int(item.get("max_quantity"))
            if max_quantity is not None and max_quantity < default_quantity:
                max_quantity = default_quantity
            display_order = max(0, int(item.get("display_order") or idx))
            description = (item.get("description") or "")[:5000]
            AccommodationExtraCharge.objects.create(
                accommodation=acc,
                code=code,
                name=name,
                description=description,
                charge_type=charge_type,
                amount=amount,
                currency=currency,
                is_optional=is_optional,
                default_quantity=default_quantity,
                max_quantity=max_quantity,
                is_active=True,
                display_order=display_order,
            )

    # Reseñas: crear desde reviews y actualizar rating_avg/review_count
    reviews_data = validated.get("reviews")
    if reviews_data:
        _save_accommodation_reviews(acc, reviews_data)
    elif validated.get("rating_avg") is not None or validated.get("review_count") is not None:
        if validated.get("rating_avg") is not None:
            try:
                r = round(float(validated["rating_avg"]), 1)
                r = max(1.0, min(5.0, r))
                acc.rating_avg = Decimal(str(r))
            except (TypeError, ValueError):
                pass
        if validated.get("review_count") is not None:
            acc.review_count = max(0, int(validated["review_count"]))
        acc.save(update_fields=["rating_avg", "review_count"])

    gallery_items = _build_gallery_items_with_urls(acc, request)
    predefined = [{"value": c[0], "label": c[1]} for c in ROOM_CATEGORIES]
    room_categories = predefined + [{"value": "unclassified", "label": "Sin clasificar"}]

    return Response(
        {
            "id": str(acc.id),
            "title": acc.title,
            "slug": acc.slug,
            "public_code": acc.public_code or None,
            "public_code_prefix": acc.public_code_prefix or None,
            "display_order": acc.display_order,
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
            "amenities": acc.amenities or [],
            "not_amenities": acc.not_amenities or [],
            "photo_count": len(gallery_items),
            "gallery_items": gallery_items,
            "room_categories": room_categories,
            "extra_charges": [
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
            ],
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH", "PUT"])
@permission_classes([IsSuperUser])
def update_accommodation_from_json(request, accommodation_id):
    """
    PATCH/PUT /api/v1/superadmin/accommodations/<uuid>/from-json/
    Body: { "accommodation_data": { ... } } — same shape as create-from-json; all fields optional.
    Updates only the provided fields. Returns full accommodation detail (same as GET).
    """
    try:
        acc = Accommodation.objects.filter(
            id=accommodation_id,
            deleted_at__isnull=True,
        ).select_related("organizer", "rental_hub", "hotel").get()
    except (Accommodation.DoesNotExist, ValueError):
        return Response(
            {"detail": "Alojamiento no encontrado."},
            status=status.HTTP_404_NOT_FOUND,
        )

    data = request.data or {}
    accommodation_data = data.get("accommodation_data")
    if accommodation_data is None:
        accommodation_data = data
    if not accommodation_data or not isinstance(accommodation_data, dict):
        return Response(
            {"detail": "Se requiere 'accommodation_data' (objeto) en el body."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = JsonAccommodationCreateSerializer(data=accommodation_data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    validated = serializer.validated_data
    update_fields = []

    if "title" in validated and validated["title"]:
        acc.title = (validated["title"] or "").strip()[:255]
        update_fields.append("title")
    if "slug" in validated:
        slug_raw = (validated["slug"] or "").strip()
        if slug_raw:
            if Accommodation.objects.filter(slug=slug_raw, deleted_at__isnull=True).exclude(id=acc.id).exists():
                return Response(
                    {"detail": f"Ya existe un alojamiento con slug '{slug_raw}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            acc.slug = slug_raw
            update_fields.append("slug")
    if "description" in validated:
        acc.description = (validated["description"] or "").strip()
        update_fields.append("description")
    if "short_description" in validated:
        acc.short_description = (validated["short_description"] or "").strip()[:500]
        update_fields.append("short_description")
    if "status" in validated and validated["status"] in ("draft", "published", "cancelled"):
        acc.status = validated["status"]
        update_fields.append("status")
    if "property_type" in validated and validated["property_type"] in dict(Accommodation.PROPERTY_TYPE_CHOICES):
        acc.property_type = validated["property_type"]
        update_fields.append("property_type")
    for field in ("location_name", "location_address", "country", "city"):
        if field in validated:
            setattr(acc, field, (validated[field] or "").strip()[:255] if field != "location_address" else (validated[field] or "").strip())
            update_fields.append(field)
    for field in ("guests", "bedrooms", "beds"):
        if field in validated:
            v = validated[field]
            if v is not None:
                n = max(0, int(v)) if field != "guests" else max(1, int(v))
                setattr(acc, field, n)
                update_fields.append(field)
    full, half = _bathrooms_from_validated(validated)
    if "full_bathrooms" in validated or "half_bathrooms" in validated or "bathrooms" in validated:
        acc.full_bathrooms = full
        acc.half_bathrooms = half
        update_fields.extend(["full_bathrooms", "half_bathrooms"])
    if "price" in validated and validated["price"] is not None:
        raw = Decimal(str(validated["price"]))
        if raw < 0:
            raw = Decimal("0")
        acc.price = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        update_fields.append("price")
    if "currency" in validated and validated.get("currency"):
        acc.currency = str(validated["currency"])[:3]
        update_fields.append("currency")
    for field in ("latitude", "longitude"):
        if field in validated:
            v = validated[field]
            if v is None:
                setattr(acc, field, None)
            else:
                try:
                    setattr(acc, field, Decimal(str(v)))
                except (TypeError, ValueError):
                    pass
            update_fields.append(field)
    if "amenities" in validated:
        acc.amenities = [str(x) for x in (validated["amenities"] or []) if x]
        update_fields.append("amenities")
    if "not_amenities" in validated:
        acc.not_amenities = [str(x) for x in (validated["not_amenities"] or []) if x]
        update_fields.append("not_amenities")
    if "organizer_id" in validated:
        oid = validated["organizer_id"]
        if oid:
            try:
                acc.organizer = Organizer.objects.get(id=oid)
            except (Organizer.DoesNotExist, ValueError):
                return Response({"detail": "Organizador no encontrado."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            acc.organizer = None
        update_fields.append("organizer_id")
    if "rental_hub_id" in validated:
        from apps.accommodations.models import RentalHub
        rid = validated["rental_hub_id"]
        if rid:
            try:
                acc.rental_hub = RentalHub.objects.get(id=rid)
            except (RentalHub.DoesNotExist, ValueError):
                return Response({"detail": "Central de arrendamiento no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            acc.rental_hub = None
        update_fields.append("rental_hub_id")
    if "hotel_id" in validated:
        hid = validated["hotel_id"]
        if hid:
            try:
                acc.hotel = Hotel.objects.get(id=hid)
            except (Hotel.DoesNotExist, ValueError):
                return Response({"detail": "Hotel no encontrado."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            acc.hotel = None
        update_fields.append("hotel_id")
    if "inherit_location_from_hotel" in validated:
        acc.inherit_location_from_hotel = bool(validated["inherit_location_from_hotel"])
        update_fields.append("inherit_location_from_hotel")
    if "inherit_amenities_from_hotel" in validated:
        acc.inherit_amenities_from_hotel = bool(validated["inherit_amenities_from_hotel"])
        update_fields.append("inherit_amenities_from_hotel")
    if "room_type_code" in validated:
        acc.room_type_code = (validated.get("room_type_code") or "").strip()[:30]
        update_fields.append("room_type_code")
    if "external_id" in validated:
        acc.external_id = (validated.get("external_id") or "").strip()[:255]
        update_fields.append("external_id")
    for field in ("unit_type", "tower", "unit_number"):
        if field in validated:
            setattr(acc, field, (validated[field] or "").strip()[:30] if field != "unit_number" else (validated[field] or "").strip()[:20])
            update_fields.append(field)
    if "floor" in validated:
        acc.floor = _optional_int(validated["floor"])
        update_fields.append("floor")
    if "square_meters" in validated:
        acc.square_meters = _optional_decimal(validated["square_meters"])
        update_fields.append("square_meters")
    if "min_nights" in validated:
        acc.min_nights = _optional_int(validated["min_nights"])
        update_fields.append("min_nights")
    if "images" in validated and validated["images"]:
        acc.images = [str(u) for u in validated["images"] if u][:50]
        update_fields.append("images")
    if "gallery_media_ids" in validated and validated["gallery_media_ids"]:
        acc.gallery_media_ids = [str(u) for u in validated["gallery_media_ids"] if u][:50]
        update_fields.append("gallery_media_ids")
    if "display_order" in validated and validated.get("display_order") is not None:
        try:
            do = max(1, int(validated["display_order"]))
            acc.display_order = do
            update_fields.append("display_order")
        except (TypeError, ValueError):
            pass
    if "public_code_prefix" in validated:
        acc.public_code_prefix = (validated.get("public_code_prefix") or "").strip()[:30]
        update_fields.append("public_code_prefix")

    # Al publicar: generar public_code (y display_order si no está definido)
    if acc.status == "published":
        for f in ensure_public_code_on_publish(acc):
            if f not in update_fields:
                update_fields.append(f)

    # Reseñas: si se envía "reviews", reemplazar todas; luego recalcular rating_avg/review_count
    if "reviews" in validated:
        AccommodationReview.objects.filter(accommodation=acc).delete()
        _save_accommodation_reviews(acc, validated["reviews"])
    if "rating_avg" in validated and validated["rating_avg"] is not None and "reviews" not in validated:
        try:
            r = round(float(validated["rating_avg"]), 1)
            r = max(1.0, min(5.0, r))
            acc.rating_avg = Decimal(str(r))
            update_fields.append("rating_avg")
        except (TypeError, ValueError):
            pass
    if "review_count" in validated and validated["review_count"] is not None and "reviews" not in validated:
        acc.review_count = max(0, int(validated["review_count"]))
        update_fields.append("review_count")

    # Extra charges (from-json): full list sync, same logic as PATCH
    if "extra_charges" in validated and isinstance(validated.get("extra_charges"), list):
        kept_ids = []
        for idx, item in enumerate(validated["extra_charges"]):
            if not isinstance(item, dict):
                continue
            code = (item.get("code") or "").strip()[:64]
            if not code:
                continue
            name = (item.get("name") or "").strip()[:255]
            charge_type = (item.get("charge_type") or "per_stay")[:20]
            if charge_type not in ("per_stay", "per_night"):
                charge_type = "per_stay"
            try:
                amount = Decimal(str(item.get("amount") or 0))
                if amount < 0:
                    amount = Decimal("0")
            except (TypeError, ValueError):
                amount = Decimal("0")
            currency = (item.get("currency") or "").strip()[:3] or None
            is_optional = bool(item.get("is_optional", True))
            default_quantity = max(1, int(item.get("default_quantity") or 1))
            max_quantity = _optional_int(item.get("max_quantity"))
            is_active = bool(item.get("is_active", True))
            display_order = max(0, int(item.get("display_order") or idx))
            description = (item.get("description") or "")[:5000]
            extra_id = item.get("id")
            if extra_id:
                try:
                    extra = AccommodationExtraCharge.objects.get(id=extra_id, accommodation=acc)
                    extra.name = name
                    extra.charge_type = charge_type
                    extra.amount = amount
                    extra.currency = currency
                    extra.is_optional = is_optional
                    extra.default_quantity = default_quantity
                    extra.max_quantity = max_quantity
                    extra.is_active = is_active
                    extra.display_order = display_order
                    extra.description = description
                    extra.save()
                    kept_ids.append(extra.id)
                    continue
                except (AccommodationExtraCharge.DoesNotExist, ValueError):
                    pass
            extra, _ = AccommodationExtraCharge.objects.update_or_create(
                accommodation=acc,
                code=code,
                defaults={
                    "name": name,
                    "description": description,
                    "charge_type": charge_type,
                    "amount": amount,
                    "currency": currency,
                    "is_optional": is_optional,
                    "default_quantity": default_quantity,
                    "max_quantity": max_quantity,
                    "is_active": is_active,
                    "display_order": display_order,
                },
            )
            kept_ids.append(extra.id)
        acc.extra_charges.exclude(id__in=kept_ids).delete()

    if update_fields:
        acc.save(update_fields=update_fields)

    # Return same shape as GET detail
    gallery_items = _build_gallery_items_with_urls(acc, request)
    predefined = [{"value": c[0], "label": c[1]} for c in ROOM_CATEGORIES]
    custom = [
        {"value": v, "label": v}
        for v in sorted(
            {it.get("room_category") for it in (acc.gallery_items or []) if it.get("room_category")}
            - PREDEFINED_ROOM_CATEGORIES
            - {"unclassified"}
        )
    ]
    room_categories = predefined + [{"value": "unclassified", "label": "Sin clasificar"}] + custom
    payload = {
        "id": str(acc.id),
        "title": acc.title,
        "slug": acc.slug,
        "public_code": acc.public_code or None,
        "public_code_prefix": acc.public_code_prefix or None,
        "display_order": acc.display_order,
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
        "amenities": acc.amenities or [],
        "not_amenities": acc.not_amenities or [],
        "photo_count": len(gallery_items),
        "gallery_items": gallery_items,
        "room_categories": room_categories,
        "unit_type": acc.unit_type or "",
        "tower": acc.tower or "",
        "floor": acc.floor,
        "unit_number": acc.unit_number or "",
        "square_meters": float(acc.square_meters) if acc.square_meters is not None else None,
        "min_nights": acc.min_nights,
        "extra_charges": [
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
        ],
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
    return Response(payload)


def _parse_date(s):
    """Parse YYYY-MM-DD or return None."""
    if not s or not isinstance(s, str):
        return None
    try:
        from datetime import datetime
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsSuperUser])
def accommodation_blocked_dates(request, accommodation_id):
    """
    GET: list blocked dates for this accommodation. Returns { "dates": ["YYYY-MM-DD", ...] }.
    POST: add blocked date(s). Body: { "date": "YYYY-MM-DD" } for one day, or
          { "date": "YYYY-MM-DD", "date_to": "YYYY-MM-DD" } for a range (inclusive).
    DELETE: remove a blocked date. Body: { "date": "YYYY-MM-DD" }.
    """
    try:
        acc = Accommodation.objects.filter(
            id=accommodation_id,
            deleted_at__isnull=True,
        ).get()
    except (Accommodation.DoesNotExist, ValueError):
        return Response(
            {"detail": "Alojamiento no encontrado."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        dates = list(
            AccommodationBlockedDate.objects.filter(accommodation=acc)
            .order_by("date")
            .values_list("date", flat=True)
        )
        return Response({
            "dates": [d.isoformat() for d in dates],
        })

    data = request.data or {}
    date_str = (data.get("date") or "").strip()
    day = _parse_date(date_str)
    if not day:
        return Response(
            {"detail": "Se requiere 'date' en formato YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if request.method == "POST":
        from datetime import timedelta

        date_to_str = (data.get("date_to") or "").strip()
        day_to = _parse_date(date_to_str) if date_to_str else None

        if day_to is not None:
            if day_to < day:
                return Response(
                    {"detail": "'date_to' debe ser igual o posterior a 'date'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Rango: crear una fecha bloqueada por cada día [day, day_to] inclusive
            created_count = 0
            added_dates = []
            current = day
            while current <= day_to:
                _, created = AccommodationBlockedDate.objects.get_or_create(
                    accommodation=acc,
                    date=current,
                )
                if created:
                    created_count += 1
                added_dates.append(current.isoformat())
                current += timedelta(days=1)
            return Response(
                {"dates": added_dates, "created_count": created_count},
                status=status.HTTP_201_CREATED,
            )
        # Una sola fecha
        _, created = AccommodationBlockedDate.objects.get_or_create(
            accommodation=acc,
            date=day,
        )
        return Response(
            {"date": day.isoformat(), "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    if request.method == "DELETE":
        deleted, _ = AccommodationBlockedDate.objects.filter(
            accommodation=acc,
            date=day,
        ).delete()
        return Response(
            {"deleted": deleted > 0, "date": day.isoformat()},
            status=status.HTTP_200_OK,
        )

    return Response({"detail": "Método no permitido."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
