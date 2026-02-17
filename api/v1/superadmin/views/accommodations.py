"""
SuperAdmin Accommodations API.
List, detail with gallery_items + image_url, and PATCH gallery for photo tour.
"""

import logging
import uuid

from django.conf import settings as django_settings
from django.db.models import Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accommodations.models import Accommodation
from apps.accommodations.constants import ROOM_CATEGORIES, ROOM_CATEGORY_LABELS
from apps.accommodations.serializers import _normalize_media_url
from apps.media.models import MediaAsset

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)

# room_category: permite valores predefinidos O cualquier string (lugares personalizados)
PREDEFINED_ROOM_CATEGORIES = {c[0] for c in ROOM_CATEGORIES}


def _build_gallery_items_with_urls(acc, request=None):
    """
    Return gallery_items with image_url for each. If gallery_items empty but
    gallery_media_ids present, build items from gallery_media_ids (room_category=null).
    """
    items = list(acc.gallery_items or [])
    if not items and acc.gallery_media_ids:
        items = [
            {"media_id": str(mid), "room_category": None, "sort_order": i}
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
        qs = Accommodation.objects.filter(deleted_at__isnull=True).select_related("organizer")

        organizer_id = request.query_params.get("organizer_id")
        if organizer_id:
            qs = qs.filter(organizer_id=organizer_id)
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
            results.append({
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
            })
        return Response({"results": results, "count": len(results)})


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
            "status": acc.status,
            "organizer_id": str(acc.organizer_id) if acc.organizer_id else None,
            "organizer_name": acc.organizer.name if acc.organizer else None,
            "city": acc.city or "",
            "country": acc.country or "",
            "guests": acc.guests,
            "price": float(acc.price or 0),
            "currency": acc.currency or "CLP",
            "gallery_items": gallery_items,
            "room_categories": room_categories,
        })

    def patch(self, request, accommodation_id):
        """Update accommodation fields (country, city, etc.)."""
        try:
            acc = self._get_accommodation(accommodation_id)
        except (Accommodation.DoesNotExist, ValueError):
            return Response({"detail": "Alojamiento no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        updatable = {"country", "city", "title", "description", "short_description", "status"}
        updated = False
        for field in updatable:
            if field in data:
                val = data[field]
                if field in ("title", "description", "short_description", "country", "city"):
                    setattr(acc, field, str(val).strip() if val is not None else "")
                elif field == "status" and val in ("draft", "published", "cancelled"):
                    setattr(acc, field, val)
                updated = True
        if updated:
            acc.save(update_fields=[f for f in updatable if f in data])
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
            valid_room_categories = {c[0] for c in ROOM_CATEGORIES}
            if room_category is not None and room_category not in valid_room_categories:
                return Response(
                    {"detail": f"room_category inválido: '{room_category}'. Debe ser uno de: {', '.join(sorted(valid_room_categories))} o null."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sort_order = it.get("sort_order", i)
            if not isinstance(sort_order, int):
                try:
                    sort_order = int(sort_order)
                except (TypeError, ValueError):
                    sort_order = i
            normalized.append({
                "media_id": mid_str,
                "room_category": room_category,
                "sort_order": sort_order,
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

        # Save: gallery_items and sync gallery_media_ids (order by sort_order)
        ordered = sorted(normalized, key=lambda x: x["sort_order"])
        acc.gallery_items = ordered
        acc.gallery_media_ids = [it["media_id"] for it in ordered]
        update_fields = ["gallery_items", "gallery_media_ids"]
        if not ordered:
            acc.images = []
            update_fields.append("images")
        acc.save(update_fields=update_fields)

        gallery_with_urls = _build_gallery_items_with_urls(acc, request)
        return Response({
            "gallery_items": gallery_with_urls,
            "photo_count": len(gallery_with_urls),
        })
