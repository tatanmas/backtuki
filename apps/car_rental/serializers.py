"""Serializers for car_rental API (public list/detail)."""

from rest_framework import serializers

from .models import Car, CarRentalCompany


def _resolve_car_images(car, request=None):
    """Resolve car gallery to list of image URLs (first from media, then fallback images)."""
    from apps.media.models import MediaAsset

    urls = []
    if getattr(car, "gallery_media_ids", None):
        assets = MediaAsset.objects.filter(
            id__in=car.gallery_media_ids,
            deleted_at__isnull=True,
        ).order_by("id")
        for asset in assets:
            if asset.file:
                url = asset.file.url
                if request and url.startswith("/"):
                    url = request.build_absolute_uri(url)
                if url:
                    urls.append(url)
    if not urls and getattr(car, "images", None):
        for raw in car.images[:20]:
            u = raw if isinstance(raw, str) else (raw.get("url") if isinstance(raw, dict) else None)
            if u:
                urls.append(u)
    return urls


def _car_to_public_dict(car, request=None, include_conditions=False):
    """Map Car to public API shape for list/detail."""
    images = _resolve_car_images(car, request)
    company_name = car.company.name if car.company else ""
    out = {
        "id": str(car.id),
        "title": car.title,
        "slug": car.slug,
        "description": car.description or "",
        "short_description": car.short_description or "",
        "price_per_day": float(car.price_per_day or 0),
        "currency": car.currency or "CLP",
        "images": images,
        "company_id": str(car.company_id) if car.company_id else None,
        "company_name": company_name,
        "pickup_time_default": car.pickup_time_default or "",
        "return_time_default": car.return_time_default or "",
        "included": list(car.included or []),
        "not_included": list(car.not_included or []),
        "min_driver_age": car.min_driver_age,
        "transmission": car.transmission or "manual",
        "seats": car.seats,
        "bags": car.bags,
        "location": {"name": company_name, "address": ""},
    }
    if include_conditions:
        if car.inherit_company_conditions and car.company:
            out["conditions"] = car.company.conditions or {}
        else:
            out["conditions"] = car.conditions_override or {}
    return out


class PublicCarListSerializer(serializers.BaseSerializer):
    """Public list serializer for Car."""

    def to_representation(self, instance):
        request = self.context.get("request")
        return _car_to_public_dict(instance, request)


class PublicCarDetailSerializer(serializers.BaseSerializer):
    """Public detail serializer for Car (includes conditions)."""

    def to_representation(self, instance):
        request = self.context.get("request")
        return _car_to_public_dict(instance, request, include_conditions=True)
