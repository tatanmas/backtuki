"""
Organizer-scoped Accommodation API.

All views enforce ownership: only accommodations belonging to the
authenticated user's primary organizer are accessible. Fields that are
superadmin-only (payment_model, tuki_commission_rate, organizer assignment)
are never writable through these endpoints.
"""

import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes as drf_permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accommodations.constants import ROOM_CATEGORIES
from apps.accommodations.helpers import (
    PREDEFINED_ROOM_CATEGORIES,
    build_accommodation_detail_payload,
    build_gallery_items_with_urls,
    bathrooms_from_data,
    optional_decimal,
    optional_int,
    parse_date,
)
from apps.accommodations.models import Accommodation, AccommodationBlockedDate
from apps.media.models import MediaAsset
from core.permissions import HasAccommodationModule, IsOrganizer

logger = logging.getLogger(__name__)

ORGANIZER_EDITABLE_TEXT_FIELDS = (
    "title", "description", "short_description",
    "location_name", "location_address", "country", "city",
)
ORGANIZER_EDITABLE_NUMERIC_FIELDS = ("guests", "bedrooms", "full_bathrooms", "half_bathrooms", "beds")


def _get_organizer(request):
    """Return the Organizer linked to the authenticated user, or None."""
    return (
        request.user.get_primary_organizer()
        if hasattr(request.user, "get_primary_organizer")
        else None
    )


def _get_organizer_or_403(request):
    """Return organizer or a 403 Response."""
    organizer = _get_organizer(request)
    if organizer is None:
        return None, Response(
            {"detail": "No se encontró organizador asociado a este usuario."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return organizer, None


class OrganizerAccommodationListView(APIView):
    """
    GET /api/v1/organizers/accommodations/
    List accommodations owned by the authenticated organizer.
    """
    permission_classes = [IsAuthenticated, IsOrganizer, HasAccommodationModule]

    def get(self, request):
        organizer, err = _get_organizer_or_403(request)
        if err:
            return err

        qs = Accommodation.objects.filter(
            organizer=organizer,
            deleted_at__isnull=True,
        ).select_related("rental_hub", "hotel").order_by("-created_at")

        search = (request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(city__icontains=search)
                | Q(location_name__icontains=search)
            )

        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter in ("draft", "published", "cancelled"):
            qs = qs.filter(status=status_filter)

        results = []
        for acc in qs:
            principal_url = ""
            if acc.gallery_items:
                for gi in acc.gallery_items:
                    if gi.get("is_principal"):
                        mid = gi.get("media_id")
                        if mid:
                            try:
                                asset = MediaAsset.objects.get(id=mid, deleted_at__isnull=True)
                                if asset.file:
                                    raw = asset.file.url
                                    if raw.startswith(("http://", "https://")):
                                        from apps.accommodations.serializers import _normalize_media_url
                                        principal_url = _normalize_media_url(raw)
                                    else:
                                        principal_url = request.build_absolute_uri(raw)
                            except MediaAsset.DoesNotExist:
                                pass
                        break

            item = {
                "id": str(acc.id),
                "title": acc.title,
                "slug": acc.slug,
                "status": acc.status,
                "city": acc.city or "",
                "country": acc.country or "",
                "guests": acc.guests,
                "price": float(acc.price or 0),
                "currency": acc.currency or "CLP",
                "photo_count": len(acc.gallery_items or []),
                "principal_image_url": principal_url,
                "property_type": acc.property_type or "cabin",
            }
            if acc.rental_hub_id:
                item["rental_hub_id"] = str(acc.rental_hub_id)
                item["rental_hub_slug"] = acc.rental_hub.slug if acc.rental_hub else None
            if acc.hotel_id:
                item["hotel_id"] = str(acc.hotel_id)
                item["hotel_slug"] = acc.hotel.slug if acc.hotel else None
            results.append(item)

        return Response({"results": results, "count": len(results)})


class OrganizerAccommodationDetailView(APIView):
    """
    GET  /api/v1/organizers/accommodations/<uuid>/
    PATCH /api/v1/organizers/accommodations/<uuid>/

    Detail and partial update. Superadmin-only fields are excluded from
    PATCH. The response uses the shared detail payload without superadmin
    fields.
    """
    permission_classes = [IsAuthenticated, IsOrganizer, HasAccommodationModule]

    def _get_accommodation(self, request, accommodation_id):
        organizer, err = _get_organizer_or_403(request)
        if err:
            return None, err
        try:
            acc = Accommodation.objects.filter(
                id=accommodation_id,
                organizer=organizer,
                deleted_at__isnull=True,
            ).select_related("organizer", "rental_hub", "hotel").get()
            return acc, None
        except (Accommodation.DoesNotExist, ValueError):
            return None, Response(
                {"detail": "Alojamiento no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def get(self, request, accommodation_id):
        acc, err = self._get_accommodation(request, accommodation_id)
        if err:
            return err
        payload = build_accommodation_detail_payload(acc, request, include_superadmin_fields=False)
        return Response(payload)

    def patch(self, request, accommodation_id):
        acc, err = self._get_accommodation(request, accommodation_id)
        if err:
            return err

        data = request.data or {}
        update_fields = []

        for field in ORGANIZER_EDITABLE_TEXT_FIELDS:
            if field in data:
                val = data[field]
                setattr(acc, field, str(val).strip() if val is not None else "")
                update_fields.append(field)

        if "status" in data and data["status"] in ("draft", "published"):
            acc.status = data["status"]
            update_fields.append("status")

        if "property_type" in data and data["property_type"] in dict(Accommodation.PROPERTY_TYPE_CHOICES):
            acc.property_type = data["property_type"]
            update_fields.append("property_type")

        for field in ORGANIZER_EDITABLE_NUMERIC_FIELDS:
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
        # Legacy "bathrooms" → full_bathrooms + half_bathrooms
        if "bathrooms" in data and ("full_bathrooms" not in data and "half_bathrooms" not in data):
            full, half = bathrooms_from_data(data)
            acc.full_bathrooms = full
            acc.half_bathrooms = half
            update_fields.extend(["full_bathrooms", "half_bathrooms"])

        if "price" in data:
            try:
                acc.price = max(Decimal("0"), Decimal(str(data["price"])))
                update_fields.append("price")
            except (TypeError, ValueError):
                pass
        if "currency" in data and data["currency"]:
            acc.currency = str(data["currency"])[:3]
            update_fields.append("currency")

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

        if "amenities" in data and isinstance(data["amenities"], list):
            acc.amenities = [str(x) for x in data["amenities"] if x]
            update_fields.append("amenities")
        if "not_amenities" in data and isinstance(data["not_amenities"], list):
            acc.not_amenities = [str(x) for x in data["not_amenities"] if x]
            update_fields.append("not_amenities")

        for field in ("unit_type", "tower"):
            if field in data:
                setattr(acc, field, (data[field] or "").strip()[:30])
                update_fields.append(field)
        if "floor" in data:
            acc.floor = optional_int(data["floor"])
            update_fields.append("floor")
        if "unit_number" in data:
            acc.unit_number = (data["unit_number"] or "").strip()[:20]
            update_fields.append("unit_number")
        if "square_meters" in data:
            acc.square_meters = optional_decimal(data["square_meters"])
            update_fields.append("square_meters")

        if "min_nights" in data:
            acc.min_nights = optional_int(data["min_nights"])
            update_fields.append("min_nights")

        if update_fields:
            acc.save(update_fields=update_fields)

        payload = build_accommodation_detail_payload(acc, request, include_superadmin_fields=False)
        return Response(payload)


class OrganizerAccommodationGalleryView(APIView):
    """
    PATCH /api/v1/organizers/accommodations/<uuid>/gallery/
    """
    permission_classes = [IsAuthenticated, IsOrganizer, HasAccommodationModule]

    def patch(self, request, accommodation_id):
        organizer, err = _get_organizer_or_403(request)
        if err:
            return err
        try:
            acc = Accommodation.objects.filter(
                id=accommodation_id,
                organizer=organizer,
                deleted_at__isnull=True,
            ).select_related("organizer").get()
        except (Accommodation.DoesNotExist, ValueError):
            return Response(
                {"detail": "Alojamiento no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = request.data or {}
        items = data.get("gallery_items")
        if items is None:
            return Response({"detail": "gallery_items es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(items, list):
            return Response({"detail": "gallery_items debe ser una lista."}, status=status.HTTP_400_BAD_REQUEST)

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
            sort_order = it.get("sort_order", i)
            if not isinstance(sort_order, int):
                try:
                    sort_order = int(sort_order)
                except (TypeError, ValueError):
                    sort_order = i
            is_principal = bool(it.get("is_principal", False))
            normalized.append({
                "media_id": mid_str,
                "room_category": room_category,
                "sort_order": sort_order,
                "is_principal": is_principal,
            })
            media_ids.append(mid_str)

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
                        {"detail": f"El asset {a.id} no pertenece a tu organización."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        ordered = sorted(normalized, key=lambda x: x["sort_order"])
        acc.gallery_items = ordered
        acc.gallery_media_ids = [it["media_id"] for it in ordered]
        acc.images = []
        acc.save(update_fields=["gallery_items", "gallery_media_ids", "images"])

        gallery_with_urls = build_gallery_items_with_urls(acc, request)
        return Response({
            "gallery_items": gallery_with_urls,
            "photo_count": len(gallery_with_urls),
        })


@api_view(["GET", "POST", "DELETE"])
@drf_permission_classes([IsAuthenticated, IsOrganizer, HasAccommodationModule])
def organizer_accommodation_blocked_dates(request, accommodation_id):
    """
    Organizer-scoped blocked dates management.
    GET: list. POST: add (single or range). DELETE: remove single date.
    """
    organizer = _get_organizer(request)
    if organizer is None:
        return Response(
            {"detail": "No se encontró organizador."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        acc = Accommodation.objects.filter(
            id=accommodation_id,
            organizer=organizer,
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
        return Response({"dates": [d.isoformat() for d in dates]})

    data = request.data or {}
    date_str = (data.get("date") or "").strip()
    day = parse_date(date_str)
    if not day:
        return Response(
            {"detail": "Se requiere 'date' en formato YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if request.method == "POST":
        date_to_str = (data.get("date_to") or "").strip()
        day_to = parse_date(date_to_str) if date_to_str else None

        if day_to is not None:
            if day_to < day:
                return Response(
                    {"detail": "'date_to' debe ser igual o posterior a 'date'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            created_count = 0
            added_dates = []
            current = day
            while current <= day_to:
                _, created = AccommodationBlockedDate.objects.get_or_create(
                    accommodation=acc, date=current,
                )
                if created:
                    created_count += 1
                added_dates.append(current.isoformat())
                current += timedelta(days=1)
            return Response(
                {"dates": added_dates, "created_count": created_count},
                status=status.HTTP_201_CREATED,
            )

        _, created = AccommodationBlockedDate.objects.get_or_create(
            accommodation=acc, date=day,
        )
        return Response(
            {"date": day.isoformat(), "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    if request.method == "DELETE":
        deleted, _ = AccommodationBlockedDate.objects.filter(
            accommodation=acc, date=day,
        ).delete()
        return Response({"deleted": deleted > 0, "date": day.isoformat()})

    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
