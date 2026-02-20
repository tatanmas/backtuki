"""SuperAdmin: Fondo del formulario de registro Erasmus (imágenes que rotan detrás del form)."""

import logging

from django.db import models
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.erasmus.models import ErasmusRegistroBackgroundSlide
from apps.media.models import MediaAsset

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


def _slide_payload(slide):
    """Build dict for one slide (id, asset_id, asset_url, asset_filename, order)."""
    asset_url = None
    asset_filename = None
    if slide.asset_id and slide.asset and not getattr(slide.asset, "deleted_at", None):
        asset_url = getattr(slide.asset, "url", None)
        asset_filename = getattr(slide.asset, "original_filename", None)
    return {
        "id": str(slide.id),
        "asset_id": str(slide.asset_id) if slide.asset_id else None,
        "asset_url": asset_url,
        "asset_filename": asset_filename,
        "order": slide.order,
    }


@api_view(["GET"])
@permission_classes([IsSuperUser])
def erasmus_registro_background_list(request):
    """
    GET /api/v1/superadmin/erasmus-registro-background/
    Returns all slides (id, asset_id, asset_url, asset_filename, order).
    """
    slides = ErasmusRegistroBackgroundSlide.objects.all().select_related("asset").order_by("order", "id")
    result = [_slide_payload(s) for s in slides]
    return Response(result)


@api_view(["POST"])
@permission_classes([IsSuperUser])
def erasmus_registro_background_create(request):
    """
    POST /api/v1/superadmin/erasmus-registro-background/create/
    Body: { "asset_id": "uuid" } (optional). Creates new slide at end.
    """
    max_order = ErasmusRegistroBackgroundSlide.objects.aggregate(m=models.Max("order"))
    next_order = (max_order.get("m") or -1) + 1
    asset_id = request.data.get("asset_id")
    slide = ErasmusRegistroBackgroundSlide.objects.create(asset_id=None, order=next_order)
    if asset_id:
        try:
            asset = MediaAsset.objects.get(id=asset_id, deleted_at__isnull=True)
            slide.asset = asset
            slide.save(update_fields=["asset"])
        except (MediaAsset.DoesNotExist, ValidationError, TypeError, ValueError):
            pass
    return Response(_slide_payload(slide), status=status.HTTP_201_CREATED)


@api_view(["DELETE", "POST"])
@permission_classes([IsSuperUser])
def erasmus_registro_background_delete(request, pk=None):
    """
    DELETE /api/v1/superadmin/erasmus-registro-background/<pk>/
    or POST with body { "id": "uuid" }
    """
    if pk is None:
        pk = request.data.get("id")
    if not pk:
        return Response({"error": "id is required"}, status=status.HTTP_400_BAD_REQUEST)
    deleted, _ = ErasmusRegistroBackgroundSlide.objects.filter(id=pk).delete()
    if not deleted:
        return Response({"error": "Slide no encontrado"}, status=status.HTTP_404_NOT_FOUND)
    return Response({"id": str(pk), "message": "Slide eliminado"})


@api_view(["PUT", "PATCH"])
@permission_classes([IsSuperUser])
def erasmus_registro_background_assign(request):
    """
    PUT /api/v1/superadmin/erasmus-registro-background/assign/
    Body: { "id": "uuid", "asset_id": "uuid" | null }
    """
    pk = request.data.get("id")
    asset_id = request.data.get("asset_id")
    if not pk:
        return Response({"error": "id is required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        slide = ErasmusRegistroBackgroundSlide.objects.get(id=pk)
    except ErasmusRegistroBackgroundSlide.DoesNotExist:
        return Response({"error": "Slide no encontrado"}, status=status.HTTP_404_NOT_FOUND)
    if asset_id is None:
        slide.asset = None
        slide.save(update_fields=["asset"])
        return Response(_slide_payload(slide))
    try:
        asset = MediaAsset.objects.get(id=asset_id, deleted_at__isnull=True)
    except (MediaAsset.DoesNotExist, ValidationError, TypeError, ValueError):
        return Response({"error": "Asset not found"}, status=status.HTTP_404_NOT_FOUND)
    slide.asset = asset
    slide.save(update_fields=["asset"])
    return Response(_slide_payload(slide))


@api_view(["POST"])
@permission_classes([IsSuperUser])
def erasmus_registro_background_reorder(request):
    """
    POST /api/v1/superadmin/erasmus-registro-background/reorder/
    Body: { "order": ["uuid1", "uuid2", ...] }
    """
    order_ids = request.data.get("order")
    if not isinstance(order_ids, list):
        return Response({"error": "order must be a list of ids"}, status=status.HTTP_400_BAD_REQUEST)
    for i, pk in enumerate(order_ids):
        ErasmusRegistroBackgroundSlide.objects.filter(id=pk).update(order=i)
    slides = ErasmusRegistroBackgroundSlide.objects.all().select_related("asset").order_by("order", "id")
    return Response([_slide_payload(s) for s in slides])
