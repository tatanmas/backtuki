"""
SuperAdmin Destinations create-from-JSON.
POST /api/v1/superadmin/destinations/create-from-json/
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.landing_destinations.models import (
    LandingDestination,
    LandingDestinationExperience,
    LandingDestinationEvent,
)

from ..permissions import IsSuperUser
from ..serializers import JsonDestinationCreateSerializer

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsSuperUser])
def create_destination_from_json(request):
    """
    POST /api/v1/superadmin/destinations/create-from-json/
    Body: { "destination_data": { "name", "slug", ... } }
    Creates LandingDestination and relations (experience_ids, event_ids).
    """
    data = request.data or {}
    destination_data = data.get("destination_data")
    if not destination_data:
        return Response(
            {"detail": "El campo 'destination_data' es requerido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = JsonDestinationCreateSerializer(data=destination_data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    validated = serializer.validated_data
    slug = validated.get("slug")
    if LandingDestination.objects.filter(slug=slug).exists():
        return Response(
            {"detail": f"Ya existe un destino con slug '{slug}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    experience_ids = validated.pop("experience_ids", None) or destination_data.get("experience_ids") or []
    event_ids = validated.pop("event_ids", None) or destination_data.get("event_ids") or []

    dest = LandingDestination(
        name=validated.get("name"),
        slug=validated.get("slug"),
        country=validated.get("country", "Chile"),
        region=validated.get("region", ""),
        description=validated.get("description", ""),
        hero_image=validated.get("hero_image", "") or "",
        hero_media_id=validated.get("hero_media_id"),
        gallery_media_ids=validated.get("gallery_media_ids") or [],
        latitude=validated.get("latitude"),
        longitude=validated.get("longitude"),
        is_active=validated.get("is_active", True),
        images=validated.get("images") or [],
        travel_guides=validated.get("travel_guides") or [],
        transportation=validated.get("transportation") or [],
        accommodation_ids=validated.get("accommodation_ids") or [],
        featured_type=validated.get("featured_type"),
        featured_id=validated.get("featured_id"),
    )
    dest.save()

    for i, eid in enumerate(experience_ids):
        try:
            uuid_val = str(eid).strip()
            if uuid_val:
                LandingDestinationExperience.objects.create(
                    destination=dest,
                    experience_id=uuid_val,
                    order=i,
                )
        except Exception:
            pass
    for i, eid in enumerate(event_ids):
        try:
            uuid_val = str(eid).strip()
            if uuid_val:
                LandingDestinationEvent.objects.create(
                    destination=dest,
                    event_id=uuid_val,
                    order=i,
                )
        except Exception:
            pass

    logger.info(
        f"✅ [JSON_DESTINATION_CREATE] Destination '{dest.name}' created from JSON (ID: {dest.id})"
    )

    return Response(
        {
            "id": str(dest.id),
            "name": dest.name,
            "slug": dest.slug,
            "country": dest.country,
            "region": dest.region,
            "is_active": dest.is_active,
        },
        status=status.HTTP_201_CREATED,
    )
