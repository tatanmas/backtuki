"""Travel-guide-specific booking helpers for embedded experiences."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.utils import timezone

from apps.experiences.models import TourInstance


def ensure_embed_block_keys(body: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Ensure each embed_experience block has a stable block_key."""
    result: list[dict[str, Any]] = []
    for index, raw_block in enumerate(body or []):
        if not isinstance(raw_block, dict):
            result.append(raw_block)
            continue
        block = deepcopy(raw_block)
        if block.get('type') == 'embed_experience' and not str(block.get('block_key') or '').strip():
            block['block_key'] = f"guide-exp-{index + 1}"
        result.append(block)
    return result


def get_block_by_key(guide, block_key: str) -> dict[str, Any] | None:
    """Return one embed_experience block by stable block key."""
    if not block_key:
        return None
    for block in ensure_embed_block_keys(guide.body or []):
        if isinstance(block, dict) and block.get('type') == 'embed_experience' and block.get('block_key') == block_key:
            return block
    return None


def get_booking_offer_from_block(block: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return normalized guide booking config from a body block."""
    if not isinstance(block, dict):
        return None
    offer = block.get('booking_offer')
    if not isinstance(offer, dict) or not offer.get('enabled'):
        return None
    normalized = deepcopy(offer)
    slots = normalized.get('slots')
    normalized['slots'] = slots if isinstance(slots, list) else []
    normalized['selection_mode'] = normalized.get('selection_mode') or 'curated_list'
    normalized['allow_full_calendar'] = bool(normalized.get('allow_full_calendar', True))
    normalized['cta_label'] = str(normalized.get('cta_label') or 'Reservar')
    return normalized


def _serialize_slot_instance(instance: TourInstance, slot_config: dict[str, Any]) -> dict[str, Any]:
    reserved_count = instance.get_current_bookings_count()
    boost = int(slot_config.get('booked_count_boost') or 0)
    display_reserved_count = reserved_count + boost
    max_capacity = instance.max_capacity
    custom_capacity = slot_config.get('custom_capacity')
    if custom_capacity not in (None, ''):
        try:
            max_capacity = int(custom_capacity)
        except (TypeError, ValueError):
            pass
    available_spots = None if max_capacity is None else max(0, max_capacity - reserved_count)
    return {
        'id': str(instance.id),
        'start_datetime': instance.start_datetime.isoformat(),
        'end_datetime': instance.end_datetime.isoformat(),
        'language': instance.language,
        'status': instance.status,
        'max_capacity': max_capacity,
        'real_capacity': instance.max_capacity,
        'reserved_count': reserved_count,
        'display_reserved_count': display_reserved_count,
        'available_spots': available_spots,
        'is_publicly_listed': instance.is_publicly_listed,
        'display_badge': (slot_config.get('display_badge') or '').strip(),
        'source': slot_config.get('source') or 'existing_instance',
        'slot_key': slot_config.get('slot_key') or '',
        'manual_label': '',
        'manual_subtitle': '',
        'is_manual_option': False,
    }


def build_public_booking_offer(guide, block: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve inline booking config into a public, frontend-friendly payload."""
    offer = get_booking_offer_from_block(block)
    if not offer:
        return None

    slots_payload: list[dict[str, Any]] = []
    now = timezone.now()
    for raw_slot in offer.get('slots', []):
        if not isinstance(raw_slot, dict) or not raw_slot.get('is_active', True):
            continue
        if raw_slot.get('source') == 'manual_option':
            custom_capacity = raw_slot.get('custom_capacity')
            try:
                normalized_capacity = int(custom_capacity) if custom_capacity not in (None, '') else None
            except (TypeError, ValueError):
                normalized_capacity = None
            display_reserved_count = int(raw_slot.get('booked_count_boost') or 0)
            slots_payload.append({
                'id': raw_slot.get('slot_key') or '',
                'start_datetime': None,
                'end_datetime': None,
                'language': '',
                'status': 'active',
                'max_capacity': normalized_capacity,
                'real_capacity': None,
                'reserved_count': 0,
                'display_reserved_count': display_reserved_count,
                'available_spots': None if normalized_capacity is None else max(0, normalized_capacity - display_reserved_count),
                'is_publicly_listed': False,
                'display_badge': (raw_slot.get('display_badge') or '').strip(),
                'source': 'manual_option',
                'slot_key': raw_slot.get('slot_key') or '',
                'manual_label': str(raw_slot.get('manual_label') or 'Horario por coordinar'),
                'manual_subtitle': str(raw_slot.get('manual_subtitle') or 'Nos inscribimos y luego coordinamos el horario'),
                'is_manual_option': True,
                'display_order': int(raw_slot.get('display_order') or 0),
            })
            continue
        instance_id = raw_slot.get('instance_id')
        if not instance_id:
            continue
        instance = TourInstance.objects.filter(
            id=instance_id,
            experience_id=block.get('experience_id'),
            status='active',
            start_datetime__gte=now,
        ).first()
        if not instance:
            continue
        slots_payload.append({
            **_serialize_slot_instance(instance, raw_slot),
            'display_order': int(raw_slot.get('display_order') or 0),
        })

    slots_payload.sort(key=lambda item: (item['display_order'], item.get('start_datetime') or ''))

    return {
        'block_key': block.get('block_key') or '',
        'guide_id': str(guide.id),
        'guide_slug': guide.slug,
        'guide_title': guide.title,
        'experience_id': str(block.get('experience_id') or ''),
        'title_override': str(offer.get('title_override') or ''),
        'subtitle_override': str(offer.get('subtitle_override') or ''),
        'intro_text': str(offer.get('intro_text') or ''),
        'cta_label': str(offer.get('cta_label') or 'Reservar'),
        'selection_mode': offer.get('selection_mode') or 'curated_list',
        'allow_full_calendar': bool(offer.get('allow_full_calendar', True)),
        'slots': slots_payload,
    }
