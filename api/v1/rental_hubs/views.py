"""Public API for rental hubs (centrales de arrendamiento)."""

from datetime import datetime
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q, Exists, OuterRef

from apps.accommodations.models import Accommodation, AccommodationBlockedDate, AccommodationReservation, RentalHub
from apps.accommodations.serializers import PublicAccommodationListSerializer


def _parse_date(s):
    """Parse YYYY-MM-DD or return None."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _resolve_rental_hub_media_urls(hub, request):
    """Resolve hero_media_id and gallery_media_ids to URLs; fallback to hero_image/gallery."""
    hero_url = hub.hero_image or ""
    gallery_urls = list(hub.gallery or [])
    if hub.hero_media_id or (hub.gallery_media_ids and len(hub.gallery_media_ids) > 0):
        from apps.media.models import MediaAsset
        if hub.hero_media_id:
            a = MediaAsset.objects.filter(
                id=hub.hero_media_id, deleted_at__isnull=True
            ).first()
            if a and a.file:
                hero_url = request.build_absolute_uri(a.file.url) if request else (a.url or hero_url)
            elif a and getattr(a, "url", None):
                hero_url = a.url
        if hub.gallery_media_ids:
            assets = MediaAsset.objects.filter(
                id__in=[x for x in hub.gallery_media_ids if x],
                deleted_at__isnull=True,
            )
            gallery_urls = []
            for uid in hub.gallery_media_ids:
                a = next((x for x in assets if str(x.id) == str(uid)), None)
                if a and a.file:
                    gallery_urls.append(
                        request.build_absolute_uri(a.file.url) if request else (getattr(a, "url", None) or "")
                    )
                elif a and getattr(a, "url", None):
                    gallery_urls.append(a.url)
    return hero_url, gallery_urls


def _hub_to_public_dict(hub, request=None):
    """Serialize RentalHub for public API. Resolves media IDs to URLs when present."""
    hero_url, gallery_urls = _resolve_rental_hub_media_urls(hub, request)
    return {
        "id": str(hub.id),
        "slug": hub.slug,
        "name": hub.name,
        "short_description": hub.short_description or "",
        "description": hub.description or "",
        "hero_image": hero_url,
        "gallery": gallery_urls,
        "meta_title": hub.meta_title or "",
        "meta_description": hub.meta_description or "",
        "min_nights": hub.min_nights,
        "units_section_title": hub.units_section_title or "Nuestros Departamentos",
        "units_section_subtitle": hub.units_section_subtitle or "Selecciona la unidad perfecta para tu estadía",
    }


class PublicRentalHubDetailView(APIView):
    """
    GET /api/v1/rental-hubs/<slug>/
    Datos de la landing de la central (nombre, descripción, hero, galería).
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        try:
            hub = RentalHub.objects.get(slug=slug, is_active=True)
        except RentalHub.DoesNotExist:
            return Response(
                {"error": "Central no encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_hub_to_public_dict(hub, request))


class PublicRentalHubAccommodationsView(APIView):
    """
    GET /api/v1/rental-hubs/<slug>/accommodations/?check_in=YYYY-MM-DD&check_out=YYYY-MM-DD&guests=N
    Lista unidades disponibles en el rango de fechas y con capacidad para guests.
    Opcional: unit_type (A1, A2, B, C), tower (A, B).
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        try:
            hub = RentalHub.objects.get(slug=slug, is_active=True)
        except RentalHub.DoesNotExist:
            return Response(
                {"error": "Central no encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )

        check_in = _parse_date(request.query_params.get("check_in"))
        check_out = _parse_date(request.query_params.get("check_out"))
        guests_param = request.query_params.get("guests", "").strip()
        try:
            guests = int(guests_param) if guests_param else None
        except ValueError:
            guests = None
        unit_type = request.query_params.get("unit_type", "").strip().upper() or None
        tower = request.query_params.get("tower", "").strip().upper() or None

        qs = Accommodation.objects.filter(
            rental_hub=hub,
            status="published",
            deleted_at__isnull=True,
        )
        if unit_type:
            qs = qs.filter(unit_type=unit_type)
        if tower:
            qs = qs.filter(tower=tower)
        if guests is not None and guests > 0:
            qs = qs.filter(guests__gte=guests)

        # Filter by availability when dates are provided
        if check_in and check_out and check_out > check_in:
            # Exclude accommodations that have any blocked date in [check_in, check_out)
            blocked_subq = AccommodationBlockedDate.objects.filter(
                accommodation_id=OuterRef("id"),
                date__gte=check_in,
                date__lt=check_out,
            )
            qs = qs.exclude(Exists(blocked_subq))
            # Exclude accommodations with overlapping reservation (pending or paid)
            overlapping = AccommodationReservation.objects.filter(
                accommodation_id=OuterRef("id"),
                status__in=("pending", "paid"),
            ).filter(
                check_in__lt=check_out,
                check_out__gt=check_in,
            )
            qs = qs.exclude(Exists(overlapping))

        qs = qs.order_by("tower", "floor", "unit_number", "-rating_avg", "-created_at")
        serializer = PublicAccommodationListSerializer(qs, many=True, context={"request": request})
        data = serializer.data
        # Enrich with rental-hub-specific fields for listing (unit_type, tower, unit_number)
        for i, acc in enumerate(qs):
            if i < len(data):
                data[i]["unit_type"] = acc.unit_type or ""
                data[i]["tower"] = acc.tower or ""
                data[i]["floor"] = acc.floor
                data[i]["unit_number"] = acc.unit_number or ""
                data[i]["square_meters"] = float(acc.square_meters) if acc.square_meters is not None else None
        return Response(data)
