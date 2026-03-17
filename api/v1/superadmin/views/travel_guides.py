"""Superadmin views for travel guides: list, detail, CRUD, create-from-JSON."""

import logging
from datetime import datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from api.v1.superadmin.permissions import IsSuperUser
from apps.travel_guides.models import TravelGuide
from apps.travel_guides.serializers import (
    TravelGuideSerializer,
    TravelGuideListSerializer,
)
from apps.travel_guides.booking import get_block_by_key
from apps.landing_destinations.models import LandingDestination
from apps.experiences.models import Experience, TourInstance

logger = logging.getLogger(__name__)


class TravelGuideListView(APIView):
    """GET /api/v1/superadmin/travel-guides/ – list all guides. Optional filters: destination_slug, template, status."""
    permission_classes = [IsSuperUser]

    def get(self, request):
        qs = TravelGuide.objects.all().select_related('destination').order_by('display_order', '-published_at')
        destination_slug = request.query_params.get('destination_slug')
        if destination_slug:
            qs = qs.filter(destination__slug=destination_slug)
        template = request.query_params.get('template')
        if template:
            qs = qs.filter(template=template)
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        serializer = TravelGuideListSerializer(qs, many=True)
        return Response(serializer.data)


class TravelGuideDetailView(APIView):
    """GET /api/v1/superadmin/travel-guides/<id>/ – retrieve. PATCH/PUT – update. DELETE – delete."""
    permission_classes = [IsSuperUser]

    def get_object(self, guide_id):
        return TravelGuide.objects.select_related('destination').get(id=guide_id)

    def get(self, request, guide_id):
        try:
            guide = self.get_object(guide_id)
        except TravelGuide.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = TravelGuideSerializer(guide)
        return Response(serializer.data)

    def patch(self, request, guide_id):
        try:
            guide = self.get_object(guide_id)
        except TravelGuide.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = TravelGuideSerializer(guide, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        if request.data.get('status') == 'published' and not guide.published_at:
            guide.published_at = timezone.now()
            guide.save(update_fields=['published_at'])
        return Response(TravelGuideSerializer(guide).data)

    def put(self, request, guide_id):
        try:
            guide = self.get_object(guide_id)
        except TravelGuide.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = TravelGuideSerializer(guide, data=request.data, partial=False)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        if request.data.get('status') == 'published' and not guide.published_at:
            guide.published_at = timezone.now()
            guide.save(update_fields=['published_at'])
        return Response(TravelGuideSerializer(guide).data)

    def delete(self, request, guide_id):
        try:
            guide = self.get_object(guide_id)
        except TravelGuide.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        guide.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TravelGuideCreateView(APIView):
    """POST /api/v1/superadmin/travel-guides/ – create a new guide."""
    permission_classes = [IsSuperUser]

    def post(self, request):
        serializer = TravelGuideSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        guide = serializer.save()
        if request.data.get('status') == 'published' and not guide.published_at:
            guide.published_at = timezone.now()
            guide.save(update_fields=['published_at'])
        return Response(TravelGuideSerializer(guide).data, status=status.HTTP_201_CREATED)


class TravelGuideCreateHiddenInstanceView(APIView):
    """POST /api/v1/superadmin/travel-guides/<guide_id>/experience-block/<block_key>/guide-instances/"""

    permission_classes = [IsSuperUser]

    def post(self, request, guide_id, block_key):
        try:
            guide = TravelGuide.objects.get(id=guide_id)
        except TravelGuide.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        block = get_block_by_key(guide, block_key)
        if not block or block.get('type') != 'embed_experience':
            return Response({"detail": "Bloque de experiencia no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        experience_id = request.data.get('experience_id') or block.get('experience_id')
        if not experience_id:
            return Response({"detail": "experience_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            experience = Experience.objects.get(id=experience_id)
        except Experience.DoesNotExist:
            return Response({"detail": "Experiencia no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        start_raw = request.data.get('start_datetime')
        end_raw = request.data.get('end_datetime')
        if not start_raw or not end_raw:
            return Response({"detail": "start_datetime y end_datetime son requeridos."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_dt = datetime.fromisoformat(str(start_raw).replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(str(end_raw).replace('Z', '+00:00'))
        except ValueError:
            return Response({"detail": "Formato de fecha inválido. Usa ISO-8601."}, status=status.HTTP_400_BAD_REQUEST)

        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, timezone.get_current_timezone())
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
        if end_dt <= start_dt:
            return Response({"detail": "end_datetime debe ser mayor que start_datetime."}, status=status.HTTP_400_BAD_REQUEST)

        language = request.data.get('language') or 'es'
        if language not in ('es', 'en'):
            return Response({"detail": "language debe ser 'es' o 'en'."}, status=status.HTTP_400_BAD_REQUEST)

        instance = TourInstance.objects.create(
            experience=experience,
            start_datetime=start_dt,
            end_datetime=end_dt,
            language=language,
            status='active',
            max_capacity=request.data.get('max_capacity') or None,
            override_adult_price=request.data.get('override_adult_price') or None,
            override_child_price=request.data.get('override_child_price') or None,
            override_infant_price=request.data.get('override_infant_price') or None,
            notes=request.data.get('notes') or '',
            is_publicly_listed=False,
            origin_travel_guide=guide,
            origin_block_key=block_key,
        )
        return Response({
            "id": str(instance.id),
            "experience": str(instance.experience_id),
            "experience_title": instance.experience.title,
            "start_datetime": instance.start_datetime.isoformat(),
            "end_datetime": instance.end_datetime.isoformat(),
            "language": instance.language,
            "status": instance.status,
            "max_capacity": instance.max_capacity,
            "override_adult_price": instance.override_adult_price,
            "override_child_price": instance.override_child_price,
            "override_infant_price": instance.override_infant_price,
            "notes": instance.notes,
            "current_bookings_count": instance.get_current_bookings_count(),
            "available_spots": instance.get_available_spots(),
            "is_publicly_listed": instance.is_publicly_listed,
            "origin_travel_guide": str(guide.id),
            "origin_block_key": block_key,
        }, status=status.HTTP_201_CREATED)


class TravelGuideDeleteHiddenInstanceView(APIView):
    """DELETE /api/v1/superadmin/travel-guides/<guide_id>/guide-instances/<instance_id>/"""

    permission_classes = [IsSuperUser]

    def delete(self, request, guide_id, instance_id):
        try:
            guide = TravelGuide.objects.get(id=guide_id)
        except TravelGuide.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            instance = TourInstance.objects.get(
                id=instance_id,
                origin_travel_guide=guide,
                is_publicly_listed=False,
            )
        except TourInstance.DoesNotExist:
            return Response({"detail": "Instancia no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if instance.reservations.exists() or instance.bookings.exists():
            return Response(
                {"detail": "No se puede eliminar una instancia con reservas asociadas."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsSuperUser])
def create_travel_guide_from_json(request):
    """
    POST /api/v1/superadmin/travel-guides/create-from-json/
    Body: { "guide_data": { "destination_slug"?, "template", "title", "slug", "excerpt", ... }, "body": [ ... ] }
    """
    data = request.data or {}
    guide_data = data.get("guide_data") or data.get("guide")
    if not guide_data or not isinstance(guide_data, dict):
        return Response(
            {"detail": "Se requiere 'guide_data' (objeto) con al menos title y slug."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    body = data.get("body")
    if body is not None and not isinstance(body, list):
        return Response(
            {"detail": "'body' debe ser un array de bloques."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    slug = (guide_data.get("slug") or "").strip()
    if not slug:
        from django.utils.text import slugify
        slug = slugify(guide_data.get("title") or "guia")
    if TravelGuide.objects.filter(slug=slug).exists():
        return Response(
            {"detail": f"Ya existe una guía con slug '{slug}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    destination = None
    dest_slug = guide_data.get("destination_slug") or guide_data.get("destination")
    if dest_slug:
        if isinstance(dest_slug, str):
            destination = LandingDestination.objects.filter(slug=dest_slug).first()
        else:
            destination = LandingDestination.objects.filter(id=dest_slug).first()

    guide = TravelGuide(
        destination=destination,
        template=guide_data.get("template") or "editorial",
        title=(guide_data.get("title") or "").strip()[:255],
        slug=slug,
        excerpt=(guide_data.get("excerpt") or "").strip(),
        hero_media_id=guide_data.get("hero_media_id"),
        hero_image=(guide_data.get("hero_image") or "").strip()[:500],
        hero_slides=guide_data.get("hero_slides") if isinstance(guide_data.get("hero_slides"), list) else [],
        body=body if body is not None else [],
        status=guide_data.get("status") or "draft",
        published_at=timezone.now() if guide_data.get("status") == "published" else None,
        display_order=guide_data.get("display_order", 0) or 0,
        meta_title=(guide_data.get("meta_title") or "").strip()[:255],
        meta_description=(guide_data.get("meta_description") or "").strip(),
        og_image=(guide_data.get("og_image") or "").strip()[:500],
    )
    guide.save()

    logger.info("Travel guide created from JSON: %s (%s)", guide.title, guide.slug)
    return Response(
        TravelGuideSerializer(guide).data,
        status=status.HTTP_201_CREATED,
    )
