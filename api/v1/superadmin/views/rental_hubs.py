"""
Superadmin CRUD for RentalHub (centrales de arrendamiento).
List, create, retrieve, update, delete. Media resolved from hero_media_id / gallery_media_ids.
Nested: list and create accommodations (unidades: departamentos/casas) within a hub.
"""

import re
from decimal import Decimal
from rest_framework import viewsets, serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from django.utils.text import slugify

from apps.accommodations.helpers import bathrooms_from_data
from apps.accommodations.models import RentalHub, Accommodation
from ..permissions import IsSuperUser


def _resolve_hub_media_urls(hub, request):
    """Return (hero_image_url, gallery_urls_list) from hub media IDs or legacy fields."""
    hero_url = hub.hero_image or ""
    gallery_urls = list(hub.gallery or [])
    if hub.hero_media_id or (getattr(hub, "gallery_media_ids", None) and len(hub.gallery_media_ids) > 0):
        from apps.media.models import MediaAsset
        if hub.hero_media_id:
            a = MediaAsset.objects.filter(
                id=hub.hero_media_id, deleted_at__isnull=True
            ).first()
            if a and a.file:
                hero_url = request.build_absolute_uri(a.file.url) if request else (getattr(a, "url", None) or hero_url)
            elif a and getattr(a, "url", None):
                hero_url = a.url
        gallery_media_ids = getattr(hub, "gallery_media_ids", None) or []
        if gallery_media_ids:
            assets = MediaAsset.objects.filter(
                id__in=[x for x in gallery_media_ids if x],
                deleted_at__isnull=True,
            )
            gallery_urls = []
            for uid in gallery_media_ids:
                a = next((x for x in assets if str(x.id) == str(uid)), None)
                if a and a.file:
                    gallery_urls.append(
                        request.build_absolute_uri(a.file.url) if request else (getattr(a, "url", None) or "")
                    )
                elif a and getattr(a, "url", None):
                    gallery_urls.append(a.url)
    return hero_url, gallery_urls


class RentalHubSerializer(serializers.ModelSerializer):
    """Full serializer for superadmin CRUD. Includes resolved hero_image and gallery for display."""

    hero_image = serializers.SerializerMethodField()
    gallery = serializers.SerializerMethodField()
    accommodations_count = serializers.SerializerMethodField()

    class Meta:
        model = RentalHub
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
            "min_nights",
            "units_section_title",
            "units_section_subtitle",
            "accommodations_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}

    def get_hero_image(self, obj):
        request = self.context.get("request")
        url, _ = _resolve_hub_media_urls(obj, request)
        return url

    def get_gallery(self, obj):
        request = self.context.get("request")
        _, urls = _resolve_hub_media_urls(obj, request)
        return urls

    def get_accommodations_count(self, obj):
        return obj.accommodations.filter(deleted_at__isnull=True).count()


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

    def validate_slug(self, value):
        if value is not None and isinstance(value, str):
            value = value.strip().lower() or None
        if not value:
            return value
        instance = self.instance
        if instance is None:
            if RentalHub.objects.filter(slug=value).exists():
                raise serializers.ValidationError(f"Ya existe una central con slug '{value}'.")
        else:
            if RentalHub.objects.filter(slug=value).exclude(id=instance.id).exists():
                raise serializers.ValidationError(f"Ya existe una central con slug '{value}'.")
        return value

    def create(self, validated_data):
        if not validated_data.get("slug", "").strip():
            name = validated_data.get("name", "central")
            slug_base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "central"
            slug = slug_base
            n = 0
            while RentalHub.objects.filter(slug=slug).exists():
                n += 1
                slug = f"{slug_base}-{n}"
            validated_data["slug"] = slug
        return super().create(validated_data)


class RentalHubViewSet(viewsets.ModelViewSet):
    """Superadmin CRUD for rental hubs (centrales de arrendamiento). Superuser only."""

    queryset = RentalHub.objects.all().order_by("name")
    serializer_class = RentalHubSerializer
    permission_classes = [IsSuperUser]
    lookup_field = "id"
    lookup_url_kwarg = "id"

    @action(detail=True, methods=["get", "post"], url_path="accommodations")
    def accommodations(self, request, id=None):
        """
        GET: list accommodations (unidades) of this rental hub.
        POST: create a new accommodation linked to this hub (rental_hub set automatically).
        Body for POST: same as superadmin accommodations (title, status, unit_type, tower, floor, unit_number, price, guests, ...). organizer_id optional.
        """
        hub = self.get_object()
        if request.method == "GET":
            qs = Accommodation.objects.filter(
                rental_hub=hub,
                deleted_at__isnull=True,
            ).select_related("organizer").order_by("tower", "floor", "unit_number", "-created_at")
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
                    "unit_type": acc.unit_type or "",
                    "tower": acc.tower or "",
                    "floor": acc.floor,
                    "unit_number": acc.unit_number or "",
                    "square_meters": float(acc.square_meters) if acc.square_meters is not None else None,
                }
                results.append(item)
            return Response({"results": results, "count": len(results)})

        # POST: create accommodation bound to this hub
        data = request.data or {}
        title = (data.get("title") or "").strip()
        if not title:
            return Response(
                {"detail": "title es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        organizer = None
        organizer_id = data.get("organizer_id")
        if organizer_id:
            from apps.organizers.models import Organizer
            try:
                organizer = Organizer.objects.get(id=organizer_id)
            except (Organizer.DoesNotExist, ValueError):
                return Response(
                    {"detail": "Organizador no encontrado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        slug_raw = (data.get("slug") or "").strip()
        slug = slugify(title) if not slug_raw else slugify(slug_raw)
        if not slug:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "alojamiento"
        # Slug must be unique globally for Accommodation
        if Accommodation.objects.filter(slug=slug, deleted_at__isnull=True).exists():
            return Response(
                {"detail": f"Ya existe un alojamiento con slug '{slug}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            rental_hub=hub,
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
            full_bathrooms=bathrooms_from_data(data)[0],
            half_bathrooms=bathrooms_from_data(data)[1],
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

        return Response(
            {
                "id": str(acc.id),
                "title": acc.title,
                "slug": acc.slug,
                "status": acc.status,
                "rental_hub_id": str(hub.id),
                "rental_hub_slug": hub.slug,
                "unit_type": acc.unit_type or "",
                "tower": acc.tower or "",
                "floor": acc.floor,
                "unit_number": acc.unit_number or "",
                "square_meters": float(acc.square_meters) if acc.square_meters is not None else None,
                "guests": acc.guests,
                "price": float(acc.price or 0),
                "currency": acc.currency or "CLP",
            },
            status=status.HTTP_201_CREATED,
        )
