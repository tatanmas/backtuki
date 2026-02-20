"""SuperAdmin: TUKI Creators landing slots (assign MediaAssets to hero, bento, etc.)."""

import logging
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.creators.models import PlatformLandingSlot
from apps.media.models import MediaAsset, MediaUsage

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)

DEFAULT_SLOT_KEYS = ['creators_landing_hero', 'creators_landing_bento_1', 'creators_landing_bento_2']

# Map slot_key to field_name for MediaUsage
SLOT_FIELD_NAMES = {
    'creators_landing_hero': 'slot_hero',
    'creators_landing_bento_1': 'slot_bento',
    'creators_landing_bento_2': 'slot_bento',
}


@api_view(['GET'])
@permission_classes([IsSuperUser])
def creators_landing_slots_list(request):
    """
    GET /api/v1/superadmin/creators-landing-slots/
    Returns list of slots with slot_key, asset_id, asset_url, asset_filename.
    """
    for key in DEFAULT_SLOT_KEYS:
        PlatformLandingSlot.objects.get_or_create(slot_key=key, defaults={'asset_id': None})
    slots = PlatformLandingSlot.objects.filter(slot_key__in=DEFAULT_SLOT_KEYS).select_related('asset')
    result = []
    for slot in slots:
        item = {
            'slot_key': slot.slot_key,
            'asset_id': str(slot.asset_id) if slot.asset_id else None,
            'asset_url': slot.asset.url if slot.asset_id and slot.asset and not slot.asset.deleted_at else None,
            'asset_filename': slot.asset.original_filename if slot.asset_id and slot.asset else None,
        }
        result.append(item)
    return Response(result)


def _sync_media_usage_for_slot(slot, new_asset):
    """
    Create or update MediaUsage so "Dónde se está utilizando" shows Creators slots.
    Soft-delete previous asset's usage; create usage for new asset.
    """
    slot_ct = ContentType.objects.get_for_model(PlatformLandingSlot)
    field_name = SLOT_FIELD_NAMES.get(slot.slot_key, 'slot_asset')

    # Soft-delete any existing MediaUsage for this slot (previous asset)
    MediaUsage.objects.filter(
        content_type=slot_ct,
        object_id=slot.id,
        deleted_at__isnull=True,
    ).update(deleted_at=timezone.now())

    # Create MediaUsage for new asset
    if new_asset:
        MediaUsage.objects.create(
            asset=new_asset,
            content_type=slot_ct,
            object_id=slot.id,
            field_name=field_name,
        )


@api_view(['PUT', 'PATCH'])
@permission_classes([IsSuperUser])
def creators_landing_slots_assign(request):
    """
    PUT /api/v1/superadmin/creators-landing-slots/assign/
    Body: { "slot_key": "creators_landing_hero", "asset_id": "uuid" | null }
    """
    slot_key = request.data.get('slot_key')
    asset_id = request.data.get('asset_id')
    if not slot_key:
        return Response({'error': 'slot_key is required'}, status=status.HTTP_400_BAD_REQUEST)
    if slot_key not in DEFAULT_SLOT_KEYS:
        return Response({'error': f'slot_key must be one of {DEFAULT_SLOT_KEYS}'}, status=status.HTTP_400_BAD_REQUEST)
    slot, _ = PlatformLandingSlot.objects.get_or_create(slot_key=slot_key, defaults={'asset_id': None})
    if asset_id is None:
        _sync_media_usage_for_slot(slot, None)
        slot.asset = None
        slot.save(update_fields=['asset'])
        return Response({'slot_key': slot_key, 'asset_id': None, 'message': 'Slot unassigned'})
    try:
        asset = MediaAsset.objects.get(id=asset_id, deleted_at__isnull=True)
    except (MediaAsset.DoesNotExist, ValidationError, TypeError, ValueError):
        return Response({'error': 'Asset not found'}, status=status.HTTP_404_NOT_FOUND)
    slot.asset = asset
    slot.save(update_fields=['asset'])
    _sync_media_usage_for_slot(slot, asset)
    return Response({
        'slot_key': slot_key,
        'asset_id': str(asset.id),
        'asset_url': asset.url,
        'asset_filename': asset.original_filename,
    })
