"""
Superadmin CRUD for Hotel. List, create, retrieve, update, delete.
Nested: list rooms (accommodations with hotel_id). Create/update from JSON.
"""

import re
from decimal import Decimal
from rest_framework import viewsets, serializers, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from django.utils.text import slugify

from apps.accommodations.models import Hotel, Accommodation
from ..permissions import IsSuperUser


def _resolve_hotel_media_urls(hotel, request):
    """Return (hero_url, gallery_urls_list) from hotel media IDs."""
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


class HotelSerializer(serializers.ModelSerializer):
    """Full serializer for superadmin CRUD. Includes resolved hero_image and gallery."""

    hero_image = serializers.SerializerMethodField()
    gallery = serializers.SerializerMethodField()
    rooms_count = serializers.SerializerMethodField()

    class Meta:
        model = Hotel
        fields = [
            "id",
            "slug",
            "name",
            "short_description",
            "description",
            "hero_media_id",
            "gallery_media_ids",
            "hero_image",
            "gallery",
            "meta_title",
            "meta_description",
            "is_active",
            "location_name",
            "location_address",
            "city",
            "country",
            "latitude",
            "longitude",
            "amenities",
            "external_id",
            "min_nights",
            "rooms_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}

    def get_hero_image(self, obj):
        request = self.context.get("request")
        url, _ = _resolve_hotel_media_urls(obj, request)
        return url

    def get_gallery(self, obj):
        request = self.context.get("request")
        _, urls = _resolve_hotel_media_urls(obj, request)
        return urls

    def get_rooms_count(self, obj):
        return obj.rooms.filter(deleted_at__isnull=True).count()

    def validate_slug(self, value):
        if value is not None and isinstance(value, str):
            value = value.strip().lower() or None
        if not value:
            return value
        instance = self.instance
        if instance is None:
            if Hotel.objects.filter(slug=value).exists():
                raise serializers.ValidationError(f"Ya existe un hotel con slug '{value}'.")
        else:
            if Hotel.objects.filter(slug=value).exclude(id=instance.id).exists():
                raise serializers.ValidationError(f"Ya existe un hotel con slug '{value}'.")
        return value

    def create(self, validated_data):
        if not validated_data.get("slug", "").strip():
            name = validated_data.get("name", "hotel")
            slug_base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "hotel"
            slug = slug_base
            n = 0
            while Hotel.objects.filter(slug=slug).exists():
                n += 1
                slug = f"{slug_base}-{n}"
            validated_data["slug"] = slug
        return super().create(validated_data)


class HotelViewSet(viewsets.ModelViewSet):
    """Superadmin CRUD for hotels. Superuser only."""

    queryset = Hotel.objects.all().order_by("name")
    serializer_class = HotelSerializer
    permission_classes = [IsSuperUser]
    lookup_field = "id"
    lookup_url_kwarg = "id"

    @action(detail=True, methods=["get"], url_path="rooms")
    def rooms(self, request, id=None):
        """GET: list rooms (accommodations) of this hotel."""
        hotel = self.get_object()
        qs = Accommodation.objects.filter(
            hotel=hotel,
            deleted_at__isnull=True,
        ).select_related("organizer").order_by("-rating_avg", "-created_at")
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
                "inherit_location_from_hotel": acc.inherit_location_from_hotel,
                "inherit_amenities_from_hotel": acc.inherit_amenities_from_hotel,
                "room_type_code": acc.room_type_code or "",
                "external_id": acc.external_id or "",
            }
            results.append(item)
        return Response({"results": results, "count": len(results)})


def _optional_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


@api_view(["POST"])
@permission_classes([IsSuperUser])
def create_hotel_from_json(request):
    """
    POST /api/v1/superadmin/hotels/create-from-json/
    Body: { "hotel_data": { "name", "slug", "short_description", "description", "hero_media_id", "gallery_media_ids",
           "meta_title", "meta_description", "is_active", "location_name", "location_address", "city", "country",
           "latitude", "longitude", "amenities", "external_id" } }
    """
    data = request.data or {}
    hotel_data = data.get("hotel_data")
    if not hotel_data:
        return Response(
            {"detail": "El campo 'hotel_data' es requerido."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    name = (hotel_data.get("name") or "").strip()
    if not name:
        return Response(
            {"detail": "name es requerido en hotel_data."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    slug_raw = (hotel_data.get("slug") or "").strip()
    slug = slugify(name) if not slug_raw else slugify(slug_raw)
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "hotel"
    if Hotel.objects.filter(slug=slug).exists():
        return Response(
            {"detail": f"Ya existe un hotel con slug '{slug}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    hotel = Hotel(
        name=name,
        slug=slug,
        short_description=(hotel_data.get("short_description") or "").strip()[:500],
        description=(hotel_data.get("description") or "").strip(),
        hero_media_id=hotel_data.get("hero_media_id"),
        gallery_media_ids=hotel_data.get("gallery_media_ids") if isinstance(hotel_data.get("gallery_media_ids"), list) else [],
        meta_title=(hotel_data.get("meta_title") or "").strip()[:255],
        meta_description=(hotel_data.get("meta_description") or "").strip()[:500],
        is_active=hotel_data.get("is_active", True),
        location_name=(hotel_data.get("location_name") or "").strip()[:255],
        location_address=(hotel_data.get("location_address") or "").strip(),
        city=(hotel_data.get("city") or "").strip()[:255],
        country=(hotel_data.get("country") or "Chile").strip()[:255],
        latitude=_optional_decimal(hotel_data.get("latitude")),
        longitude=_optional_decimal(hotel_data.get("longitude")),
        amenities=[str(x) for x in (hotel_data.get("amenities") or []) if x],
        external_id=(hotel_data.get("external_id") or "").strip()[:255],
    )
    hotel.save()
    return Response(
        {"id": str(hotel.id), "slug": hotel.slug, "name": hotel.name},
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH"])
@permission_classes([IsSuperUser])
def update_hotel_from_json(request, hotel_id):
    """
    PATCH /api/v1/superadmin/hotels/<hotel_id>/from-json/
    Body: { "hotel_data": { ... } } — same shape as create; only provided fields are updated.
    """
    try:
        hotel = Hotel.objects.get(id=hotel_id)
    except (Hotel.DoesNotExist, ValueError):
        return Response(
            {"detail": "Hotel no encontrado."},
            status=status.HTTP_404_NOT_FOUND,
        )
    data = request.data or {}
    hotel_data = data.get("hotel_data")
    if not hotel_data:
        return Response(
            {"detail": "El campo 'hotel_data' es requerido."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if "name" in hotel_data and hotel_data["name"]:
        hotel.name = (hotel_data["name"] or "").strip()[:255]
    if "slug" in hotel_data:
        slug = (hotel_data["slug"] or "").strip().lower()
        if slug and slug != hotel.slug and Hotel.objects.filter(slug=slug).exclude(id=hotel.id).exists():
            return Response(
                {"detail": f"Ya existe un hotel con slug '{slug}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if slug:
            hotel.slug = slug
    if "short_description" in hotel_data:
        hotel.short_description = (hotel_data["short_description"] or "").strip()[:500]
    if "description" in hotel_data:
        hotel.description = (hotel_data["description"] or "").strip()
    if "hero_media_id" in hotel_data:
        hotel.hero_media_id = hotel_data["hero_media_id"]
    if "gallery_media_ids" in hotel_data and isinstance(hotel_data["gallery_media_ids"], list):
        hotel.gallery_media_ids = hotel_data["gallery_media_ids"]
    if "meta_title" in hotel_data:
        hotel.meta_title = (hotel_data["meta_title"] or "").strip()[:255]
    if "meta_description" in hotel_data:
        hotel.meta_description = (hotel_data["meta_description"] or "").strip()[:500]
    if "is_active" in hotel_data:
        hotel.is_active = bool(hotel_data["is_active"])
    if "location_name" in hotel_data:
        hotel.location_name = (hotel_data["location_name"] or "").strip()[:255]
    if "location_address" in hotel_data:
        hotel.location_address = (hotel_data["location_address"] or "").strip()
    if "city" in hotel_data:
        hotel.city = (hotel_data["city"] or "").strip()[:255]
    if "country" in hotel_data:
        hotel.country = (hotel_data["country"] or "Chile").strip()[:255]
    if "latitude" in hotel_data:
        hotel.latitude = _optional_decimal(hotel_data["latitude"])
    if "longitude" in hotel_data:
        hotel.longitude = _optional_decimal(hotel_data["longitude"])
    if "amenities" in hotel_data and isinstance(hotel_data["amenities"], list):
        hotel.amenities = [str(x) for x in hotel_data["amenities"] if x]
    if "external_id" in hotel_data:
        hotel.external_id = (hotel_data["external_id"] or "").strip()[:255]
    hotel.save()
    return Response({"id": str(hotel.id), "slug": hotel.slug, "name": hotel.name})
