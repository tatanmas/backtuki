"""
Process free tour operator commands from WhatsApp group messages.
All commands MUST start with "Tuki " (or "TUKI ", "tuki/") so only intentional operator
messages are processed (e.g. "Tuki bloquear fecha 15/03/2025").
"""

import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from django.utils import timezone

from apps.experiences.models import Experience, TourInstance, TourBooking
from apps.whatsapp.models import ExperienceGroupBinding, WhatsAppChat
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService

logger = logging.getLogger(__name__)

# Prefix required so normal messages with "bloquear"/"desbloquear" are not treated as commands
COMMAND_PREFIX = r'^\s*tuki[\s/]+'
COMMAND_PREFIX_RE = re.compile(COMMAND_PREFIX, re.IGNORECASE)


class FreeTourCommandParser:
    """Parse operator command and date/language from message text. Requires 'Tuki ' prefix."""

    # Date patterns: DD/MM/YYYY, YYYY-MM-DD, D/M/YYYY
    DATE_PATTERNS = [
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', lambda m: (int(m.group(3)), int(m.group(2)), int(m.group(1)))),  # YYYY-MM-DD
        (r'(\d{1,2})/(\d{1,2})/(\d{2,4})', lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)) if len(m.group(3)) == 4 else 2000 + int(m.group(3)))),  # DD/MM/YY or YYYY
    ]

    @classmethod
    def parse_date(cls, text: str) -> Optional[str]:
        """Extract a date and return YYYY-MM-DD or None."""
        for pattern, extract in cls.DATE_PATTERNS:
            m = re.search(pattern, text)
            if m:
                try:
                    day, month, year = extract(m)
                    if 1 <= month <= 12 and 1 <= day <= 31 and year >= 2020:
                        return f"{year:04d}-{month:02d}-{day:02d}"
                except (ValueError, IndexError):
                    continue
        return None

    @classmethod
    def parse_language(cls, text: str) -> Optional[str]:
        """Extract es or en from message (español, spanish, en, english, inglés)."""
        t = text.lower().strip()
        if re.search(r'\b(español|español|es)\b', t):
            return 'es'
        if re.search(r'\b(english|ingles|inglés|en)\b', t):
            return 'en'
        return None

    @classmethod
    def parse(cls, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse message into command + params.
        Message MUST start with "Tuki " or "Tuki/" (case-insensitive) to be recognized.
        Returns dict with action ('block'|'unblock'|'inscritos'|'cupos'), date, language.
        """
        if not text or not isinstance(text, str):
            return None
        raw = text.strip()
        if not raw:
            return None
        # Require prefix so "bloquear" / "desbloquear" in normal chat are ignored
        match = COMMAND_PREFIX_RE.match(raw)
        if not match:
            return None
        t = raw[match.end():].strip().lower()
        if not t:
            return None
        date = cls.parse_date(t)
        lang = cls.parse_language(t)

        if re.search(r'\bbloquear\s+fecha\b|\bbloquear\s+\d', t):
            return {'action': 'block', 'date': date, 'language': lang}
        if re.search(r'\bdesbloquear\s+fecha\b|\bdesbloquear\s+\d', t):
            return {'action': 'unblock', 'date': date, 'language': lang}
        if re.search(r'\binscritos\b|\blista\b', t):
            return {'action': 'inscritos', 'date': date or cls.parse_date(t) or timezone.now().strftime('%Y-%m-%d'), 'language': None}
        if re.search(r'\bcupos\b', t):
            return {'action': 'cupos', 'date': date or timezone.now().strftime('%Y-%m-%d'), 'language': None}

        return None


def get_experience_for_group_chat(chat_id: str) -> Optional[Experience]:
    """Return the first active free tour experience linked to this WhatsApp group chat_id."""
    try:
        chat = WhatsAppChat.objects.filter(chat_id=chat_id, type='group').first()
        if not chat:
            return None
        binding = (
            ExperienceGroupBinding.objects.filter(
                whatsapp_group=chat,
                is_active=True,
                experience__is_free_tour=True,
                experience__deleted_at__isnull=True,
            )
            .select_related('experience')
            .first()
        )
        return binding.experience if binding else None
    except Exception as e:
        logger.debug("get_experience_for_group_chat failed: %s", e)
        return None


def execute_command(experience: Experience, action: str, date: Optional[str], language: Optional[str]) -> str:
    """Execute the command and return a short reply message."""
    if action == 'block' and date:
        qs = TourInstance.objects.filter(
            experience=experience,
            start_datetime__date=datetime.strptime(date, '%Y-%m-%d').date(),
            status='active',
        )
        if language in ('es', 'en'):
            qs = qs.filter(language=language)
        n = qs.update(status='blocked')
        return f"✅ Bloqueada fecha {date}" + (f" ({language})" if language else " (ambos idiomas)") + f". {n} instancia(s)."
    if action == 'unblock' and date:
        qs = TourInstance.objects.filter(
            experience=experience,
            start_datetime__date=datetime.strptime(date, '%Y-%m-%d').date(),
            status='blocked',
        )
        if language in ('es', 'en'):
            qs = qs.filter(language=language)
        n = qs.update(status='active')
        return f"✅ Desbloqueada fecha {date}" + (f" ({language})" if language else "") + f". {n} instancia(s)."
    if action == 'inscritos' and date:
        instances = TourInstance.objects.filter(
            experience=experience,
            start_datetime__date=datetime.strptime(date, '%Y-%m-%d').date(),
        ).order_by('start_datetime')
        lines = [f"Inscritos {date}:"]
        for inst in instances:
            bookings = list(TourBooking.objects.filter(tour_instance=inst, status='confirmed').order_by('created_at'))
            lang = inst.get_language_display() if inst.language else 'Español'
            lines.append(f"\n{inst.start_datetime.strftime('%H:%M')} {lang}:")
            if not bookings:
                lines.append("  (ninguno)")
            for b in bookings:
                lines.append(f"  • {b.first_name} {b.last_name} — {b.participants_count} pax — {b.email} — {b.phone or '—'}")
        return "\n".join(lines) if len("\n".join(lines)) < 3000 else "\n".join(lines)[:2990] + "\n..."
    if action == 'cupos':
        target_date = date or timezone.now().strftime('%Y-%m-%d')
        instances = TourInstance.objects.filter(
            experience=experience,
            start_datetime__date=datetime.strptime(target_date, '%Y-%m-%d').date(),
        ).order_by('start_datetime')
        lines = [f"Cupos {target_date}:"]
        for inst in instances:
            lang = inst.get_language_display() if inst.language else 'Español'
            avail = inst.get_available_spots()
            cap = inst.max_capacity
            lines.append(f"  {inst.start_datetime.strftime('%H:%M')} {lang}: {inst.get_current_bookings_count()}/{cap} ocupados" + (f", {avail} libres" if avail is not None else ""))
        return "\n".join(lines) if lines else f"No hay instancias para {target_date}."
    return "Comando no reconocido."


def process_and_reply(message_content: str, chat_id: str) -> bool:
    """
    If the message is a free tour command from a linked group, execute it and send reply.
    Returns True if a command was handled and reply sent.
    """
    parsed = FreeTourCommandParser.parse(message_content or "")
    if not parsed:
        return False
    experience = get_experience_for_group_chat(chat_id)
    if not experience:
        return False
    reply = execute_command(
        experience,
        parsed['action'],
        parsed.get('date'),
        parsed.get('language'),
    )
    try:
        service = WhatsAppWebService()
        service.send_message('', reply, group_id=chat_id)
        logger.info("Free tour command replied in group %s: %s", chat_id, parsed['action'])
        return True
    except Exception as e:
        logger.exception("Failed to send free tour command reply: %s", e)
        return False
