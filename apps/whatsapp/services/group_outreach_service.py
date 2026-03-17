"""
Group outreach service: first-message automation for WhatsApp group participants.

Sends a single initial message to participants who:
- Are not in the exclude list
- Have not already received an outreach message for this group
- Do not have an existing individual chat with us (no prior conversation)
- Optionally are not saved contacts (skip_saved_contacts=True)

Uses random message from template list and human-like delays to reduce spam detection risk.
"""
import logging
import random
import re
from typing import Dict, List, Optional

from django.db import transaction
from django.db.utils import IntegrityError
from django.utils import timezone

from apps.whatsapp.models import (
    GroupOutreachConfig,
    GroupOutreachSent,
    WhatsAppChat,
    WhatsAppMessage,
)
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService

logger = logging.getLogger(__name__)


def _normalize_phone(value: str) -> str:
    """Return digits-only phone for comparison."""
    if not value:
        return ""
    return re.sub(r"\D", "", value)


def _participant_phone_normalized(participant: dict) -> str:
    """Extract normalized phone from participant (id or phone field)."""
    pid = participant.get("id") or ""
    phone = participant.get("phone") or ""
    if phone:
        return _normalize_phone(str(phone))
    if "@c.us" in pid:
        return (pid.split("@")[0] or "").strip()
    if "@lid" in pid:
        return (pid.replace("@lid", "") or "").strip()
    return _normalize_phone(pid)


def get_eligible_participants(
    config: GroupOutreachConfig,
    group_info: dict,
    saved_contact_map: Optional[Dict[str, bool]] = None,
) -> List[dict]:
    """
    From group_info['participants'], return list of participants that are eligible
    for first message (not excluded, not already sent, no prior chat, optionally not saved).
    """
    participants = group_info.get("participants") or []
    if not participants:
        return []

    exclude_normalized = set()
    for num in (config.exclude_numbers or []):
        n = _normalize_phone(str(num))
        if n:
            exclude_normalized.add(n)

    already_sent_ids = set(
        GroupOutreachSent.objects.filter(config=config).values_list(
            "participant_id", flat=True
        )
    )

    # Chats we have with this contact (individual): any chat with chat_id = participant_id
    # or phone matching (for @c.us we can also check WhatsAppMessage.phone)
    participant_ids = [p.get("id") for p in participants if p.get("id")]
    existing_chat_ids = set(
        WhatsAppChat.objects.filter(
            chat_id__in=participant_ids,
            type="individual",
        ).values_list("chat_id", flat=True)
    )

    # Also consider: if we have any message to/from this phone, we have conversed
    all_phones_in_messages = set(
        WhatsAppMessage.objects.values_list("phone", flat=True).distinct()
    )
    # Normalize for comparison
    existing_phones = set(_normalize_phone(p) for p in all_phones_in_messages if p)

    saved_contact_map = saved_contact_map or {}

    eligible = []
    for p in participants:
        pid = p.get("id")
        if not pid:
            continue
        if pid in already_sent_ids:
            continue
        phone_norm = _participant_phone_normalized(p)
        if phone_norm and phone_norm in exclude_normalized:
            continue
        if pid in existing_chat_ids:
            continue
        if phone_norm and phone_norm in existing_phones:
            continue
        if config.skip_saved_contacts and saved_contact_map.get(pid) is True:
            continue
        eligible.append(p)

    return eligible


def run_outreach_for_config(config: GroupOutreachConfig) -> Dict[str, int]:
    """
    Run one outreach cycle for the given config.
    Uses cached_eligible_participants when available (no Node call); otherwise fetches from Node and saves rest to cache.
    Sends up to max_per_run first messages with random template and delay.
    Returns dict with sent, skipped, error counts.
    """
    if not config.enabled:
        return {"sent": 0, "skipped": 0, "errors": 0}

    group = config.group
    if group.type != "group":
        logger.warning(f"Outreach config {config.id} group is not type=group, skipping")
        return {"sent": 0, "skipped": 0, "errors": 0}

    templates = (config.message_templates or []) if isinstance(config.message_templates, list) else []
    if not templates or not any(t and str(t).strip() for t in templates):
        logger.warning(f"Outreach config {config.id} has no message_templates, skipping")
        config.last_run_at = timezone.now()
        config.save(update_fields=["last_run_at"])
        return {"sent": 0, "skipped": 0, "errors": 0}

    service = WhatsAppWebService()
    max_send = max(1, min(config.max_per_run, 5))
    sent = 0
    errors = 0

    # Un envío por iteración: lock corto para "reservar" un elegible, luego enviar fuera del lock
    for idx in range(max_send):
        participant = None
        with transaction.atomic():
            config_locked = GroupOutreachConfig.objects.select_for_update().get(pk=config.pk)
            cached = [p for p in (getattr(config_locked, "cached_eligible_participants", None) or []) if p.get("id")]
            cached = _filter_cache_not_sent(config_locked, cached)
            if not cached:
                break
            participant = random.choice(cached)
            pid = participant.get("id")
            cached = [p for p in cached if p.get("id") != pid]
            config_locked.cached_eligible_participants = cached
            config_locked.cached_eligible_count = max(0, (config_locked.cached_eligible_count or 0) - 1)
            config_locked.last_run_at = timezone.now()
            config_locked.save(update_fields=["cached_eligible_participants", "cached_eligible_count", "last_run_at"])

        if participant is None:
            break

        # Enviar fuera del lock (evita retener BD durante delay y envío)
        if idx > 0:
            delay = random.randint(
                max(1, config.min_delay_seconds),
                max(config.min_delay_seconds, config.max_delay_seconds),
            )
            try:
                import time
                time.sleep(delay)
            except Exception:
                pass

        pid = participant.get("id")
        phone_norm = participant.get("phone_normalized") or ""
        phone_clean = WhatsAppWebService.clean_phone_number(phone_norm) if phone_norm else (pid.split("@")[0] if pid and "@" in pid else None)
        msg_index = random.randint(0, len(templates) - 1)
        message_text = templates[msg_index]
        if not message_text or not message_text.strip():
            continue

        try:
            if pid and "@lid" in pid:
                service.send_message("", message_text, chat_id=pid)
            else:
                service.send_message(phone_clean or phone_norm or pid, message_text)
            try:
                GroupOutreachSent.objects.create(
                    config=config,
                    participant_id=pid,
                    phone_normalized=phone_norm,
                    message_used=message_text,
                    message_index=msg_index,
                )
            except IntegrityError:
                logger.warning(f"Outreach duplicate create for {pid} (config {config.id}), skipping")
                continue
            sent += 1
            logger.info(f"Outreach sent to {pid} for group {group.chat_id}")
        except Exception as e:
            logger.exception(f"Outreach send failed to {pid}: {e}")
            errors += 1

    if sent > 0 or errors > 0:
        return {"sent": sent, "skipped": 0, "errors": errors}

    # Sin caché: obtener del Node, enviar y guardar el resto en BD
    try:
        group_info = service.get_group_info(group.chat_id)
    except Exception as e:
        logger.exception(f"Failed to get group info for {group.chat_id}: {e}")
        return {"sent": 0, "skipped": 0, "errors": 1}

    participants = group_info.get("participants") or []
    if not participants:
        config.last_run_at = timezone.now()
        config.save(update_fields=["last_run_at"])
        return {"sent": 0, "skipped": 0, "errors": 0}

    saved_contact_map = {}
    if config.skip_saved_contacts:
        ids_to_check = [p.get("id") for p in participants if p.get("id")]
        try:
            saved_contact_map = service.check_saved_contacts(ids_to_check)
        except Exception as e:
            logger.warning(f"Check saved contacts failed, treating all as not saved: {e}")

    eligible = get_eligible_participants(config, group_info, saved_contact_map)
    if not eligible:
        config.last_run_at = timezone.now()
        config.save(update_fields=["last_run_at"])
        return {"sent": 0, "skipped": len(participants), "errors": 0}

    max_send = max(1, min(config.max_per_run, 5))
    to_send = list(eligible)
    random.shuffle(to_send)
    to_send = to_send[:max_send]

    sent = 0
    errors = 0
    sent_ids = set()
    for idx, participant in enumerate(to_send):
        pid = participant.get("id")
        phone = participant.get("phone") or (pid.split("@")[0] if pid and "@" in pid else pid)
        phone_clean = WhatsAppWebService.clean_phone_number(phone) if phone else None

        msg_index = random.randint(0, len(templates) - 1)
        message_text = templates[msg_index]
        if not message_text or not message_text.strip():
            continue

        if idx > 0:
            delay = random.randint(
                max(1, config.min_delay_seconds),
                max(config.min_delay_seconds, config.max_delay_seconds),
            )
            try:
                import time
                time.sleep(delay)
            except Exception:
                pass

        try:
            if pid and "@lid" in pid:
                service.send_message("", message_text, chat_id=pid)
            else:
                service.send_message(phone_clean or phone or pid, message_text)
            GroupOutreachSent.objects.create(
                config=config,
                participant_id=pid,
                phone_normalized=_participant_phone_normalized(participant),
                message_used=message_text,
                message_index=msg_index,
            )
            sent += 1
            sent_ids.add(pid)
            logger.info(f"Outreach sent to {pid} for group {group.chat_id}")
        except Exception as e:
            logger.exception(f"Outreach send failed to {pid}: {e}")
            errors += 1

    # Guardar el resto de elegibles en BD para próximos runs
    remaining = [p for p in eligible if p.get("id") not in sent_ids]
    config.cached_eligible_participants = _eligible_to_minimal(remaining)
    config.cached_eligible_count = len(remaining)
    config.cached_eligible_at = timezone.now()
    config.last_run_at = timezone.now()
    config.save(update_fields=[
        "cached_eligible_participants", "cached_eligible_count", "cached_eligible_at", "last_run_at"
    ])

    return {
        "sent": sent,
        "skipped": len(participants) - len(to_send) + (len(to_send) - sent - errors),
        "errors": errors,
    }


def _eligible_to_minimal(eligible: List[dict]) -> List[dict]:
    """Convert list of participant dicts to minimal format for cache: [{id, phone_normalized}]."""
    return [
        {"id": p.get("id"), "phone_normalized": _participant_phone_normalized(p)}
        for p in eligible
        if p.get("id")
    ]


def _filter_cache_not_sent(config: GroupOutreachConfig, cached: List[dict]) -> List[dict]:
    """Quita de la lista en caché a quienes ya tienen GroupOutreachSent (evita reenvío y caché obsoleta)."""
    if not cached:
        return []
    pids = [p.get("id") for p in cached if p.get("id")]
    already_sent = set(
        GroupOutreachSent.objects.filter(config=config, participant_id__in=pids).values_list(
            "participant_id", flat=True
        )
    )
    return [p for p in cached if p.get("id") not in already_sent]


def send_one_outreach_now(config: GroupOutreachConfig) -> Dict:
    """
    Send one outreach message to a randomly chosen eligible participant (manual "send now").
    Uses cached_eligible_participants when available; otherwise fetches from Node and saves the rest to cache.
    Returns {"sent": True, "participant_id": "...", "phone_normalized": "..."} or
    {"sent": False, "error": "..."}.
    """
    group = config.group
    if group.type != "group":
        return {"sent": False, "error": "Chat is not a group"}

    templates = (config.message_templates or []) if isinstance(config.message_templates, list) else []
    valid_templates = [t for t in templates if t and str(t).strip()]
    if not valid_templates:
        return {"sent": False, "error": "No hay mensajes de inicio configurados"}

    service = WhatsAppWebService()

    # Reservar un elegible con lock para evitar doble asignación con Celery
    participant = None
    with transaction.atomic():
        config_locked = GroupOutreachConfig.objects.select_for_update().get(pk=config.pk)
        cached = [p for p in (getattr(config_locked, "cached_eligible_participants", None) or []) if p.get("id")]
        cached = _filter_cache_not_sent(config_locked, cached)
        if cached:
            participant = random.choice(cached)
            pid = participant.get("id")
            cached = [p for p in cached if p.get("id") != pid]
            config_locked.cached_eligible_participants = cached
            config_locked.cached_eligible_count = max(0, (config_locked.cached_eligible_count or 0) - 1)
            config_locked.last_run_at = timezone.now()
            config_locked.save(update_fields=["cached_eligible_participants", "cached_eligible_count", "last_run_at"])

    if participant:
        pid = participant.get("id")
        phone_norm = participant.get("phone_normalized") or ""
        message_text = random.choice(valid_templates)
        msg_index = templates.index(message_text) if message_text in templates else 0
        try:
            if pid and "@lid" in pid:
                service.send_message("", message_text, chat_id=pid)
            else:
                phone_clean = WhatsAppWebService.clean_phone_number(phone_norm) if phone_norm else (pid.split("@")[0] if pid else None)
                service.send_message(phone_clean or phone_norm or pid, message_text)
        except Exception as e:
            logger.exception(f"Outreach send_one failed to {pid}: {e}")
            return {"sent": False, "error": str(e)}
        try:
            GroupOutreachSent.objects.create(
                config=config,
                participant_id=pid,
                phone_normalized=phone_norm,
                message_used=message_text,
                message_index=msg_index,
            )
        except IntegrityError:
            logger.warning(f"Outreach send_one duplicate for {pid}, already sent")
            return {"sent": False, "error": "Este contacto ya recibió el mensaje"}
        logger.info(f"Outreach send_one sent to {pid} for group {group.chat_id}")
        return {"sent": True, "participant_id": pid, "phone_normalized": phone_norm}

    # Sin caché: obtener del Node y guardar el resto en BD
    try:
        group_info = service.get_group_info(group.chat_id)
    except Exception as e:
        logger.exception(f"Failed to get group info for {group.chat_id}: {e}")
        return {"sent": False, "error": str(e)}

    participants = group_info.get("participants") or []
    if not participants:
        return {"sent": False, "error": "No hay participantes en el grupo"}

    saved_contact_map = {}
    if config.skip_saved_contacts:
        ids_to_check = [p.get("id") for p in participants if p.get("id")]
        try:
            saved_contact_map = service.check_saved_contacts(ids_to_check)
        except Exception as e:
            logger.warning(f"Check saved contacts failed: {e}")

    eligible = get_eligible_participants(config, group_info, saved_contact_map)
    if not eligible:
        return {"sent": False, "error": "No hay elegibles (todos tienen conversación previa o ya recibieron mensaje)"}

    participant = random.choice(eligible)
    pid = participant.get("id")
    phone = participant.get("phone") or (pid.split("@")[0] if pid and "@" in pid else pid)
    phone_clean = WhatsAppWebService.clean_phone_number(phone) if phone else None

    message_text = random.choice(valid_templates)
    msg_index = templates.index(message_text) if message_text in templates else 0

    try:
        if pid and "@lid" in pid:
            service.send_message("", message_text, chat_id=pid)
        else:
            service.send_message(phone_clean or phone or pid, message_text)
    except Exception as e:
        logger.exception(f"Outreach send_one failed to {pid}: {e}")
        return {"sent": False, "error": str(e)}

    GroupOutreachSent.objects.create(
        config=config,
        participant_id=pid,
        phone_normalized=_participant_phone_normalized(participant),
        message_used=message_text,
        message_index=msg_index,
    )

    # Guardar el resto de elegibles en BD para próximos envíos
    remaining = [p for p in eligible if p.get("id") != pid]
    config.cached_eligible_participants = _eligible_to_minimal(remaining)
    config.cached_eligible_count = len(remaining)
    config.cached_eligible_at = timezone.now()
    config.last_run_at = timezone.now()
    config.save(update_fields=[
        "cached_eligible_participants", "cached_eligible_count", "cached_eligible_at", "last_run_at"
    ])

    logger.info(f"Outreach send_one sent to {pid} for group {group.chat_id}")
    return {
        "sent": True,
        "participant_id": pid,
        "phone_normalized": _participant_phone_normalized(participant),
    }
