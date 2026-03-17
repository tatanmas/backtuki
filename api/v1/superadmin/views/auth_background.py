"""SuperAdmin: Fondo de login/auth (imágenes que rotan en login, registro, organizer login)."""

from django.db import models
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.models import AuthBackgroundSlide
from apps.media.models import MediaAsset

from ..permissions import IsSuperUser


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


def _build_absolute_url(request, raw_url):
    """Turn relative URL into absolute for public API."""
    if not raw_url:
        return None
    if raw_url.startswith(("http://", "https://")):
        return raw_url
    path = raw_url.lstrip("/")
    return request.build_absolute_uri(f"/{path}" if path else "/")


# ---------- Public API (no auth) ----------


@api_view(["GET"])
@permission_classes([AllowAny])
def auth_background_public_list(request):
    """
    GET /api/v1/site/auth-background/
    Returns { "urls": ["https://...", ...] } for login/register background. No auth required.
    """
    slides = AuthBackgroundSlide.objects.filter(
        asset__isnull=False
    ).select_related("asset").order_by("order", "id")
    urls = []
    for slide in slides:
        if not slide.asset or getattr(slide.asset, "deleted_at", None):
            continue
        raw_url = getattr(slide.asset, "url", None) if slide.asset else None
        if not raw_url:
            continue
        url = _build_absolute_url(request, raw_url)
        if url:
            urls.append(url)
    return Response({"urls": urls})


# ---------- SuperAdmin CRUD ----------


@api_view(["GET"])
@permission_classes([IsSuperUser])
def auth_background_list(request):
    """
    GET /api/v1/superadmin/auth-background/
    Returns all slides (id, asset_id, asset_url, asset_filename, order).
    """
    slides = AuthBackgroundSlide.objects.all().select_related("asset").order_by("order", "id")
    return Response([_slide_payload(s) for s in slides])


@api_view(["POST"])
@permission_classes([IsSuperUser])
def auth_background_create(request):
    """
    POST /api/v1/superadmin/auth-background/create/
    Body: { "asset_id": "uuid" } (optional). Creates new slide at end.
    """
    max_order = AuthBackgroundSlide.objects.aggregate(m=models.Max("order"))
    next_order = (max_order.get("m") or -1) + 1
    asset_id = request.data.get("asset_id")
    slide = AuthBackgroundSlide.objects.create(asset_id=None, order=next_order)
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
def auth_background_delete(request, pk=None):
    """
    DELETE /api/v1/superadmin/auth-background/<pk>/
    or POST with body { "id": "uuid" }
    """
    if pk is None:
        pk = request.data.get("id")
    if not pk:
        return Response({"error": "id is required"}, status=status.HTTP_400_BAD_REQUEST)
    deleted, _ = AuthBackgroundSlide.objects.filter(id=pk).delete()
    if not deleted:
        return Response({"error": "Slide no encontrado"}, status=status.HTTP_404_NOT_FOUND)
    return Response({"id": str(pk), "message": "Slide eliminado"})


@api_view(["PUT", "PATCH"])
@permission_classes([IsSuperUser])
def auth_background_assign(request):
    """
    PUT /api/v1/superadmin/auth-background/assign/
    Body: { "id": "uuid", "asset_id": "uuid" | null }
    """
    pk = request.data.get("id")
    asset_id = request.data.get("asset_id")
    if not pk:
        return Response({"error": "id is required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        slide = AuthBackgroundSlide.objects.get(id=pk)
    except AuthBackgroundSlide.DoesNotExist:
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
def auth_background_reorder(request):
    """
    POST /api/v1/superadmin/auth-background/reorder/
    Body: { "order": ["uuid1", "uuid2", ...] }
    """
    order_ids = request.data.get("order")
    if not isinstance(order_ids, list):
        return Response({"error": "order must be a list of ids"}, status=status.HTTP_400_BAD_REQUEST)
    for i, pk in enumerate(order_ids):
        AuthBackgroundSlide.objects.filter(id=pk).update(order=i)
    slides = AuthBackgroundSlide.objects.all().select_related("asset").order_by("order", "id")
    return Response([_slide_payload(s) for s in slides])
