"""Public API for hotels: detail by slug and list rooms (with optional availability filter)."""

from datetime import datetime
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Exists, OuterRef

from apps.accommodations.models import Accommodation, AccommodationBlockedDate, AccommodationReservation, Hotel
from apps.accommodations.serializers import resolve_room_public_payload


def _parse_date(s):
    """Parse YYYY-MM-DD or return None."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _resolve_hotel_media_urls(hotel, request):
    """Resolve hero_media_id and gallery_media_ids to URLs."""
    hero_url = ""
    gallery_urls = []
    if hotel.hero_media_id or (hotel.gallery_media_ids and len(hotel.gallery_media_ids) > 0):
        from apps.media.models import MediaAsset
        if hotel.hero_media_id:
            a = MediaAsset.objects.filter(
                id=hotel.hero_media_id, deleted_at__isnull=True
            ).first()
            if a and a.file:
                hero_url = request.build_absolute_uri(a.file.url) if request else (getattr(a, "url", None) or "")
            elif a and getattr(a, "url", None):
                hero_url = a.url
        if hotel.gallery_media_ids:
            assets = MediaAsset.objects.filter(
                id__in=[x for x in hotel.gallery_media_ids if x],
                deleted_at__isnull=True,
            )
            for uid in hotel.gallery_media_ids:
                a = next((x for x in assets if str(x.id) == str(uid)), None)
                if a and a.file:
                    gallery_urls.append(
                        request.build_absolute_uri(a.file.url) if request else (getattr(a, "url", None) or "")
                    )
                elif a and getattr(a, "url", None):
                    gallery_urls.append(a.url)
    return hero_url, gallery_urls


def _hotel_to_public_dict(hotel, request=None):
    """Serialize Hotel for public API."""
    hero_url, gallery_urls = _resolve_hotel_media_urls(hotel, request)
    lat = float(hotel.latitude) if hotel.latitude is not None else 0
    lng = float(hotel.longitude) if hotel.longitude is not None else 0
    return {
        "id": str(hotel.id),
        "slug": hotel.slug,
        "name": hotel.name,
        "short_description": hotel.short_description or "",
        "description": hotel.description or "",
        "hero_image": hero_url,
        "gallery": gallery_urls,
        "meta_title": hotel.meta_title or "",
        "meta_description": hotel.meta_description or "",
        "location": {
            "name": hotel.location_name or hotel.city or hotel.country or "",
            "address": hotel.location_address or None,
            "city": hotel.city or "",
            "country": hotel.country or "Chile",
            "coordinates": {"lat": lat, "lng": lng},
        },
        "amenities": list(hotel.amenities or []),
    }


class PublicHotelDetailView(APIView):
    """
    GET /api/v1/hotels/<slug>/
    Hotel detail for landing (name, description, hero, gallery, location, amenities).
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        try:
            hotel = Hotel.objects.get(slug=slug, is_active=True)
        except Hotel.DoesNotExist:
            return Response(
                {"error": "Hotel no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_hotel_to_public_dict(hotel, request))


class PublicHotelRoomsView(APIView):
    """
    GET /api/v1/hotels/<slug>/rooms/?check_in=YYYY-MM-DD&check_out=YYYY-MM-DD&guests=N
    List published rooms with optional availability filter. Payload includes inheritance (location, amenities from hotel).
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        try:
            hotel = Hotel.objects.get(slug=slug, is_active=True)
        except Hotel.DoesNotExist:
            return Response(
                {"error": "Hotel no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )

        check_in = _parse_date(request.query_params.get("check_in"))
        check_out = _parse_date(request.query_params.get("check_out"))
        guests_param = request.query_params.get("guests", "").strip()
        try:
            guests = int(guests_param) if guests_param else None
        except ValueError:
            guests = None

        qs = Accommodation.objects.filter(
            hotel=hotel,
            status="published",
            deleted_at__isnull=True,
        )
        if guests is not None and guests > 0:
            qs = qs.filter(guests__gte=guests)

        if check_in and check_out and check_out > check_in:
            blocked_subq = AccommodationBlockedDate.objects.filter(
                accommodation_id=OuterRef("id"),
                date__gte=check_in,
                date__lt=check_out,
            )
            qs = qs.exclude(Exists(blocked_subq))
            overlapping = AccommodationReservation.objects.filter(
                accommodation_id=OuterRef("id"),
                status__in=("pending", "paid"),
            ).filter(
                check_in__lt=check_out,
                check_out__gt=check_in,
            )
            qs = qs.exclude(Exists(overlapping))

        qs = qs.order_by("-rating_avg", "-created_at")
        data = [resolve_room_public_payload(acc, request) for acc in qs]
        return Response(data)
