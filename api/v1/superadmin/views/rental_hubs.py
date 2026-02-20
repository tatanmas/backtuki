"""
Superadmin CRUD for RentalHub (centrales de arrendamiento).
List, create, retrieve, update, delete. Media resolved from hero_media_id / gallery_media_ids.
"""

import re
from rest_framework import viewsets, serializers

from apps.accommodations.models import RentalHub
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
