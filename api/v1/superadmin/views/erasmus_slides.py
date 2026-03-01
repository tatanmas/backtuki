"""SuperAdmin: Erasmus slider slides (assign MediaAssets to hero slides)."""

import logging
import uuid
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.erasmus.models import ErasmusSlideConfig
from apps.media.models import MediaAsset, MediaUsage

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)

# Solo para asegurar que existan 3 slides iniciales la primera vez
DEFAULT_SLIDE_IDS = ['sunset-manquehue', 'valpo-concon', 'san-cristobal-bike']


def _sync_media_usage_for_slide(config, new_asset):
    """
    Create or update MediaUsage so "Dónde se está utilizando" shows Erasmus slides.
    """
    config_ct = ContentType.objects.get_for_model(ErasmusSlideConfig)

    MediaUsage.objects.filter(
        content_type=config_ct,
        object_id=config.id,
        deleted_at__isnull=True,
    ).update(deleted_at=timezone.now())

    if new_asset:
        MediaUsage.objects.create(
            asset=new_asset,
            content_type=config_ct,
            object_id=config.id,
            field_name='erasmus_slide',
        )


@api_view(['GET'])
@permission_classes([IsSuperUser])
def erasmus_slides_list(request):
    """
    GET /api/v1/superadmin/erasmus-slides/
    Returns all slides (slide_id, asset_id, asset_url, asset_filename, order).
    """
    from django.db import models
    for i, slide_id in enumerate(DEFAULT_SLIDE_IDS):
        ErasmusSlideConfig.objects.get_or_create(
            slide_id=slide_id,
            defaults={'asset_id': None, 'order': i},
        )
    configs = ErasmusSlideConfig.objects.all().select_related('asset').order_by('order', 'slide_id')
    result = []
    for i, cfg in enumerate(configs):
        asset_url = None
        asset_filename = None
        if cfg.asset_id and cfg.asset and not getattr(cfg.asset, 'deleted_at', None):
            asset_url = cfg.asset.url
            asset_filename = getattr(cfg.asset, 'original_filename', None)
        result.append({
            'slide_id': cfg.slide_id,
            'asset_id': str(cfg.asset_id) if cfg.asset_id else None,
            'asset_url': asset_url,
            'asset_filename': asset_filename,
            'caption': getattr(cfg, 'caption', '') or '',
            'order': i,
        })
    return Response(result)


@api_view(['POST'])
@permission_classes([IsSuperUser])
def erasmus_slides_create(request):
    """
    POST /api/v1/superadmin/erasmus-slides/create/
    Body: {}  -> creates new slide with slide_id=uuid, order=max+1.
    """
    from django.db import models
    max_order = ErasmusSlideConfig.objects.aggregate(m=models.Max('order'))
    next_order = (max_order.get('m') or -1) + 1
    new_slide_id = str(uuid.uuid4())
    ErasmusSlideConfig.objects.create(slide_id=new_slide_id, asset_id=None, order=next_order)
    return Response({
        'slide_id': new_slide_id,
        'order': next_order,
        'asset_id': None,
        'asset_url': None,
        'asset_filename': None,
        'caption': '',
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE', 'POST'])
@permission_classes([IsSuperUser])
def erasmus_slides_delete(request, slide_id=None):
    """
    DELETE /api/v1/superadmin/erasmus-slides/<slide_id>/
    or POST with body { "slide_id": "..." }
    """
    if slide_id is None:
        slide_id = request.data.get('slide_id')
    if not slide_id:
        return Response({'error': 'slide_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    if slide_id in DEFAULT_SLIDE_IDS:
        return Response({'error': 'No se puede eliminar un slide inicial; quita solo la imagen con "Quitar".'}, status=status.HTTP_400_BAD_REQUEST)
    deleted, _ = ErasmusSlideConfig.objects.filter(slide_id=slide_id).delete()
    if not deleted:
        return Response({'error': 'Slide no encontrado'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'slide_id': slide_id, 'message': 'Slide eliminado'})


@api_view(['PUT', 'PATCH'])
@permission_classes([IsSuperUser])
def erasmus_slides_assign(request):
    """
    PUT /api/v1/superadmin/erasmus-slides/assign/
    Body: { "slide_id": "...", "asset_id": "uuid" | null }
    Cualquier slide_id; si no existe se crea con order=max+1.
    """
    from django.db import models
    slide_id = (request.data.get('slide_id') or '').strip()
    asset_id = request.data.get('asset_id')
    if not slide_id:
        return Response({'error': 'slide_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    if slide_id not in DEFAULT_SLIDE_IDS:
        return Response(
            {'error': f'slide_id must be one of: {", ".join(DEFAULT_SLIDE_IDS)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    config = ErasmusSlideConfig.objects.filter(slide_id=slide_id).first()
    if not config:
        max_order = ErasmusSlideConfig.objects.aggregate(m=models.Max('order'))
        next_order = (max_order.get('m') or -1) + 1
        config = ErasmusSlideConfig.objects.create(
            slide_id=slide_id,
            asset_id=None,
            order=next_order,
        )
    caption = request.data.get('caption')
    if asset_id is None:
        _sync_media_usage_for_slide(config, None)
        config.asset = None
        if caption is not None:
            config.caption = caption or ''
        config.save(update_fields=['asset', 'caption'] if caption is not None else ['asset'])
        return Response({
            'slide_id': slide_id,
            'asset_id': None,
            'caption': getattr(config, 'caption', '') or '',
            'message': 'Slide unassigned',
        })
    try:
        asset = MediaAsset.objects.get(id=asset_id, deleted_at__isnull=True)
    except (MediaAsset.DoesNotExist, ValidationError, TypeError, ValueError):
        return Response({'error': 'Asset not found'}, status=status.HTTP_404_NOT_FOUND)
    config.asset = asset
    if caption is not None:
        config.caption = caption or ''
    config.save(update_fields=['asset', 'caption'] if caption is not None else ['asset'])
    _sync_media_usage_for_slide(config, asset)
    return Response({
        'slide_id': slide_id,
        'asset_id': str(asset.id),
        'asset_url': asset.url,
        'asset_filename': getattr(asset, 'original_filename', None),
        'caption': getattr(config, 'caption', '') or '',
    })


@api_view(['POST'])
@permission_classes([IsSuperUser])
def erasmus_slides_reorder(request):
    """
    POST /api/v1/superadmin/erasmus-slides/reorder/
    Body: { "order": ["slide_id1", "slide_id2", ...] }
    Updates each slide's order to its index in the list. Returns the new list.
    """
    order_slide_ids = request.data.get('order')
    if not isinstance(order_slide_ids, list):
        return Response({'error': 'order must be a list of slide_ids'}, status=status.HTTP_400_BAD_REQUEST)
    for i, slide_id in enumerate(order_slide_ids):
        if not slide_id:
            continue
        ErasmusSlideConfig.objects.filter(slide_id=slide_id).update(order=i)
    configs = ErasmusSlideConfig.objects.all().select_related('asset').order_by('order', 'slide_id')
    result = []
    for i, cfg in enumerate(configs):
        asset_url = None
        asset_filename = None
        if cfg.asset_id and cfg.asset and not getattr(cfg.asset, 'deleted_at', None):
            asset_url = cfg.asset.url
            asset_filename = getattr(cfg.asset, 'original_filename', None)
        result.append({
            'slide_id': cfg.slide_id,
            'asset_id': str(cfg.asset_id) if cfg.asset_id else None,
            'asset_url': asset_url,
            'asset_filename': asset_filename,
            'caption': getattr(cfg, 'caption', '') or '',
            'order': i,
        })
    return Response(result)
