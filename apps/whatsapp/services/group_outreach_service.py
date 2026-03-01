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
    Run one outreach cycle for the given config: fetch participants, filter eligible,
    send up to max_per_run first messages with random template and optional small delay.
    Returns dict with sent, skipped, error counts.
    """
    if not config.enabled:
        return {"sent": 0, "skipped": 0, "errors": 0}

    group = config.group
    if group.type != "group":
        logger.warning(f"Outreach config {config.id} group is not type=group, skipping")
        return {"sent": 0, "skipped": 0, "errors": 0}

    service = WhatsAppWebService()
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

    templates = (config.message_templates or []) if isinstance(config.message_templates, list) else []
    if not templates:
        logger.warning(f"Outreach config {config.id} has no message_templates, skipping")
        config.last_run_at = timezone.now()
        config.save(update_fields=["last_run_at"])
        return {"sent": 0, "skipped": len(eligible), "errors": 0}

    max_send = max(1, min(config.max_per_run, 5))
    to_send = list(eligible)
    random.shuffle(to_send)
    to_send = to_send[:max_send]

    sent = 0
    errors = 0
    for idx, participant in enumerate(to_send):
        pid = participant.get("id")
        phone = participant.get("phone") or (pid.split("@")[0] if pid and "@" in pid else pid)
        phone_clean = WhatsAppWebService.clean_phone_number(phone) if phone else None

        msg_index = random.randint(0, len(templates) - 1)
        message_text = templates[msg_index]
        if not message_text or not message_text.strip():
            continue

        # Small in-run delay (5–20 s) so not all at same second
        if idx > 0:
            delay = random.randint(5, 20)
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
            logger.info(f"Outreach sent to {pid} for group {group.chat_id}")
        except Exception as e:
            logger.exception(f"Outreach send failed to {pid}: {e}")
            errors += 1

    config.last_run_at = timezone.now()
    config.save(update_fields=["last_run_at"])

    return {
        "sent": sent,
        "skipped": len(participants) - len(to_send) + (len(to_send) - sent - errors),
        "errors": errors,
    }
