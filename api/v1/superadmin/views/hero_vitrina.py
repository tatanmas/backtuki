"""
SuperAdmin: Hero vitrina — select and order items (experiences, accommodations, events, rent-a-cars) for the landing hero slider.
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.creators.models import HeroVitrinaItem
from apps.experiences.models import Experience
from apps.accommodations.models import Accommodation
from apps.events.models import Event
from apps.car_rental.models import Car
from apps.media.models import MediaAsset

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


def _resolve_preview(content_type: str, object_id: str, request=None) -> dict:
    """Return title and image URL for a vitrina item for superadmin list display."""
    try:
        if content_type == 'experience':
            obj = Experience.objects.filter(id=object_id).first()
            if obj:
                img = None
                if getattr(obj, 'images', None) and len(obj.images) > 0:
                    first_media_id = obj.images[0] if isinstance(obj.images[0], str) else None
                    if first_media_id:
                        asset = MediaAsset.objects.filter(id=first_media_id).first()
                        if asset:
                            img = asset.url
                return {'title': obj.title, 'image_url': img, 'has_image': bool(img)}
        elif content_type == 'accommodation':
            obj = Accommodation.objects.filter(id=object_id).first()
            if obj:
                img = None
                if getattr(obj, 'images', None) and len(obj.images) > 0:
                    first_media_id = obj.images[0] if isinstance(obj.images[0], str) else None
                    if first_media_id:
                        asset = MediaAsset.objects.filter(id=first_media_id).first()
                        if asset:
                            img = asset.url
                return {'title': obj.title, 'image_url': img, 'has_image': bool(img)}
        elif content_type == 'event':
            obj = Event.objects.filter(id=object_id).first()
            if obj and hasattr(obj, 'images'):
                img = None
                first_image = obj.images.first()
                if first_image and getattr(first_image, 'image', None):
                    url = first_image.image.url
                    img = request.build_absolute_uri(url) if request else url
                return {'title': obj.title, 'image_url': img, 'has_image': bool(img)}
        elif content_type == 'rent_a_car':
            obj = Car.objects.filter(id=object_id).select_related('company').first()
            if obj:
                img = None
                if getattr(obj, 'gallery_media_ids', None) and len(obj.gallery_media_ids) > 0:
                    aid = obj.gallery_media_ids[0]
                    asset = MediaAsset.objects.filter(id=aid).first()
                    if asset:
                        img = asset.url
                if not img and obj.company and getattr(obj.company, 'hero_media_id', None):
                    asset = MediaAsset.objects.filter(id=obj.company.hero_media_id).first()
                    if asset:
                        img = asset.url
                return {'title': obj.title, 'image_url': img, 'has_image': bool(img)}
    except Exception as e:
        logger.warning("hero_vitrina preview resolve error: %s", e)
    return {'title': None, 'image_url': None, 'has_image': False}


@api_view(['GET'])
@permission_classes([IsSuperUser])
def hero_vitrina_list(request):
    """
    GET /api/v1/superadmin/hero-vitrina/
    Returns list with resolved title and image_url for display in superadmin.
    """
    items = HeroVitrinaItem.objects.all().order_by('order', 'created_at')
    result = []
    for item in items:
        preview = _resolve_preview(item.content_type, str(item.object_id), request=request)
        result.append({
            'id': str(item.id),
            'content_type': item.content_type,
            'object_id': str(item.object_id),
            'order': item.order,
            'title': preview.get('title'),
            'image_url': preview.get('image_url'),
            'has_image': preview.get('has_image', False),
        })
    return Response(result)


@api_view(['POST'])
@permission_classes([IsSuperUser])
def hero_vitrina_add(request):
    """
    POST /api/v1/superadmin/hero-vitrina/add/
    Body: { "content_type": "experience"|"accommodation"|"event"|"rent_a_car", "object_id": "uuid" }
    """
    content_type = request.data.get('content_type')
    object_id = request.data.get('object_id')
    if not content_type or not object_id:
        return Response(
            {'detail': 'content_type and object_id are required'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if content_type not in dict(HeroVitrinaItem.CONTENT_TYPE_CHOICES):
        return Response(
            {'detail': f'Invalid content_type: {content_type}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        from uuid import UUID
        uid = UUID(str(object_id))
    except (ValueError, TypeError):
        return Response(
            {'detail': 'object_id must be a valid UUID'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    from django.db.models import Max
    max_order = HeroVitrinaItem.objects.aggregate(max_o=Max('order'))
    next_order = (max_order.get('max_o') or 0) + 1
    item = HeroVitrinaItem.objects.create(
        content_type=content_type,
        object_id=uid,
        order=next_order,
    )
    preview = _resolve_preview(content_type, str(uid), request=request)
    return Response({
        'id': str(item.id),
        'content_type': item.content_type,
        'object_id': str(item.object_id),
        'order': item.order,
        'title': preview.get('title'),
        'image_url': preview.get('image_url'),
        'has_image': preview.get('has_image', False),
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE', 'POST'])
@permission_classes([IsSuperUser])
def hero_vitrina_remove(request, item_id=None):
    """
    DELETE /api/v1/superadmin/hero-vitrina/<id>/
    or POST with _method=DELETE or body { "id": "uuid" } for bulk delete.
    """
    if item_id:
        try:
            item = HeroVitrinaItem.objects.get(id=item_id)
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except HeroVitrinaItem.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    rid = request.data.get('id')
    if rid:
        try:
            item = HeroVitrinaItem.objects.get(id=rid)
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except HeroVitrinaItem.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'detail': 'id or item_id required'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsSuperUser])
def hero_vitrina_reorder(request):
    """
    POST /api/v1/superadmin/hero-vitrina/reorder/
    Body: { "order": [ "id1", "id2", ... ] }  — new order of vitrina item IDs.
    """
    order_ids = request.data.get('order')
    if not isinstance(order_ids, list) or not order_ids:
        return Response(
            {'detail': 'order must be a non-empty list of item IDs'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    items_by_id = {str(i.id): i for i in HeroVitrinaItem.objects.filter(id__in=order_ids)}
    for idx, iid in enumerate(order_ids):
        item = items_by_id.get(str(iid))
        if item:
            item.order = idx
            item.save(update_fields=['order'])
    return Response({'ok': True})
