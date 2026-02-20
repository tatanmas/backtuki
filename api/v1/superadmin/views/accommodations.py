"""
SuperAdmin Accommodations API.
List, detail with gallery_items + image_url, PATCH for full edit, POST to create.
Create-from-JSON: POST create-from-json/ with accommodation_data (organizer_id optional).
"""

import logging
import re
import uuid

from django.conf import settings as django_settings
from django.db.models import Q
from django.utils.text import slugify
from decimal import Decimal
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.accommodations.models import Accommodation
from apps.accommodations.constants import ROOM_CATEGORIES
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
    List accommodations (superuser only). Query: organizer_id, status, search.
    """
    permission_classes = [IsSuperUser]

    def get(self, request):
        qs = Accommodation.objects.filter(deleted_at__isnull=True).select_related("organizer", "rental_hub")

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

        qs = qs.order_by("-created_at")
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
        title = (data.get("title") or "").strip()
        if not title:
            return Response({"detail": "title es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        organizer = None
        if organizer_id:
            try:
                organizer = Organizer.objects.get(id=organizer_id)
            except (Organizer.DoesNotExist, ValueError):
                return Response({"detail": "Organizador no encontrado."}, status=status.HTTP_400_BAD_REQUEST)
        elif not rental_hub_id:
            return Response({"detail": "organizer_id o rental_hub_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        rental_hub = None
        if rental_hub_id:
            from apps.accommodations.models import RentalHub
            try:
                rental_hub = RentalHub.objects.get(id=rental_hub_id)
            except (RentalHub.DoesNotExist, ValueError):
                return Response({"detail": "Central de arrendamiento no encontrada."}, status=status.HTTP_400_BAD_REQUEST)

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

        acc = Accommodation(
            title=title,
            slug=slug,
            organizer=organizer,
            rental_hub=rental_hub,
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
            bathrooms=max(0, int(data.get("bathrooms", 1))),
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
        # Return same shape as GET detail
        gallery_items = _build_gallery_items_with_urls(acc, request)
        predefined = [{"value": c[0], "label": c[1]} for c in ROOM_CATEGORIES]
        custom = []
        room_categories = predefined + [{"value": "unclassified", "label": "Sin clasificar"}] + custom
        return Response({
            "id": str(acc.id),
            "title": acc.title,
            "slug": acc.slug,
            "description": acc.description or "",
            "short_description": acc.short_description or "",
            "status": acc.status,
            "property_type": acc.property_type or "cabin",
            "organizer_id": str(acc.organizer_id),
            "organizer_name": acc.organizer.name if acc.organizer else None,
            "location_name": acc.location_name or "",
            "location_address": acc.location_address or "",
            "latitude": float(acc.latitude) if acc.latitude is not None else None,
            "longitude": float(acc.longitude) if acc.longitude is not None else None,
            "city": acc.city or "",
            "country": acc.country or "",
            "guests": acc.guests,
            "bedrooms": acc.bedrooms,
            "bathrooms": acc.bathrooms,
            "beds": acc.beds,
            "price": float(acc.price or 0),
            "currency": acc.currency or "CLP",
            "amenities": acc.amenities or [],
            "not_amenities": acc.not_amenities or [],
            "photo_count": len(gallery_items),
            "gallery_items": gallery_items,
            "room_categories": room_categories,
        }, status=status.HTTP_201_CREATED)


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
        ).select_related("organizer").get()

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

        return Response({
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
            "bathrooms": acc.bathrooms,
            "beds": acc.beds,
            "price": float(acc.price or 0),
            "currency": acc.currency or "CLP",
            "amenities": acc.amenities if isinstance(acc.amenities, list) else [],
            "not_amenities": acc.not_amenities if isinstance(acc.not_amenities, list) else [],
            "photo_count": len(gallery_items),
            "gallery_items": gallery_items,
            "room_categories": room_categories,
        })

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

        # Numeric capacity
        for field in ("guests", "bedrooms", "bathrooms", "beds"):
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

        # Price
        if "price" in data:
            try:
                acc.price = Decimal(str(data["price"]))
                if acc.price < 0:
                    acc.price = Decimal("0")
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

        if update_fields:
            acc.save(update_fields=update_fields)
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

    acc = Accommodation(
        title=title,
        slug=slug,
        organizer=organizer,
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
        bathrooms=max(0, int(validated.get("bathrooms", 1))),
        beds=max(0, int(validated.get("beds", 1))) if validated.get("beds") is not None else 1,
        price=Decimal(str(validated.get("price", 0))) if validated.get("price") is not None else Decimal("0"),
        currency=(validated.get("currency") or "CLP")[:3],
        amenities=[str(x) for x in (validated.get("amenities") or []) if x],
        not_amenities=[str(x) for x in (validated.get("not_amenities") or []) if x],
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

    acc.save()

    gallery_items = _build_gallery_items_with_urls(acc, request)
    predefined = [{"value": c[0], "label": c[1]} for c in ROOM_CATEGORIES]
    room_categories = predefined + [{"value": "unclassified", "label": "Sin clasificar"}]

    return Response(
        {
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
            "bathrooms": acc.bathrooms,
            "beds": acc.beds,
            "price": float(acc.price or 0),
            "currency": acc.currency or "CLP",
            "amenities": acc.amenities or [],
            "not_amenities": acc.not_amenities or [],
            "photo_count": len(gallery_items),
            "gallery_items": gallery_items,
            "room_categories": room_categories,
        },
        status=status.HTTP_201_CREATED,
    )
