"""
Process accommodation operator commands from WhatsApp group messages.

Commands require a `Tuki` prefix and operate only on accommodations that are
reachable from the current WhatsApp group by one of these paths:
- direct accommodation -> group binding
- hotel's default group
- rental hub's default group
- accommodation -> operator binding, when that operator is linked to the group

The processor is intentionally conservative:
- it only works in groups
- it fails closed on ambiguous property matches
- it only authorizes by sender phone when the relevant operator phones are
  actually configured
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional
from urllib.parse import urlparse

from django.db.models import Q
from django.utils import timezone

from apps.accommodations.models import (
    Accommodation,
    AccommodationBlockedDate,
    AccommodationReservation,
)
from apps.whatsapp.models import (
    AccommodationGroupBinding,
    TourOperator,
    WhatsAppChat,
)
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService

logger = logging.getLogger(__name__)

COMMAND_PREFIX = r"^\s*tuki[\s/]+"
COMMAND_PREFIX_RE = re.compile(COMMAND_PREFIX, re.IGNORECASE)
DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})/(\d{1,2})/(\d{2,4})")
LINK_SLUG_RE = re.compile(r"/(?:alojamientos|accommodations|hotel|hoteles|central|centrales|rental-hubs?)/([^/?#]+)")
LIST_TERMS = ("propiedades", "alojamientos", "unidades", "habitaciones")


@dataclass
class ParsedAccommodationCommand:
    action: str
    identifier: str = ""
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class AccommodationCommandParser:
    """Parse `Tuki` commands for accommodations."""

    @classmethod
    def parse(cls, text: str) -> Optional[ParsedAccommodationCommand]:
        if not text or not isinstance(text, str):
            return None

        raw = text.strip()
        if not raw:
            return None

        match = COMMAND_PREFIX_RE.match(raw)
        if not match:
            return None

        body = raw[match.end():].strip()
        if not body:
            return None

        lowered = cls._normalize_spaces(body.lower())
        dates = cls._extract_dates(body)
        start_date = dates[0] if dates else None
        end_date = dates[1] if len(dates) > 1 else start_date

        if cls._is_list_command(lowered):
            return ParsedAccommodationCommand(action="list")

        if cls._matches_action(lowered, ("bloquear", "block")):
            return ParsedAccommodationCommand(
                action="block",
                identifier=cls._extract_identifier(body, ("bloquear", "block")),
                start_date=start_date,
                end_date=end_date,
            )

        if cls._matches_action(lowered, ("desbloquear", "liberar", "unlock", "unblock")):
            return ParsedAccommodationCommand(
                action="unblock",
                identifier=cls._extract_identifier(body, ("desbloquear", "liberar", "unlock", "unblock")),
                start_date=start_date,
                end_date=end_date,
            )

        if cls._matches_action(lowered, ("disponibilidad", "ver disponibilidad", "disponible", "availability")):
            return ParsedAccommodationCommand(
                action="availability",
                identifier=cls._extract_identifier(body, ("disponibilidad", "ver disponibilidad", "disponible", "availability")),
                start_date=start_date,
                end_date=end_date,
            )

        if cls._matches_action(
            lowered,
            ("reservas", "proximas reservas", "próximas reservas", "ver reservas", "ver proximas reservas", "ver próximas reservas"),
        ):
            return ParsedAccommodationCommand(
                action="reservations",
                identifier=cls._extract_identifier(
                    body,
                    ("reservas", "proximas reservas", "próximas reservas", "ver reservas", "ver proximas reservas", "ver próximas reservas"),
                ),
                start_date=start_date,
                end_date=end_date,
            )

        return None

    @staticmethod
    def _normalize_spaces(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _matches_action(text: str, prefixes: tuple[str, ...]) -> bool:
        return any(text.startswith(prefix) for prefix in prefixes)

    @staticmethod
    def _is_list_command(text: str) -> bool:
        return (
            text in LIST_TERMS
            or text.startswith("listar ")
            or text.startswith("lista ")
            or text.startswith("mostrar ")
        ) and any(term in text for term in LIST_TERMS)

    @classmethod
    def _extract_dates(cls, text: str) -> list[date]:
        results: list[date] = []
        for match in DATE_RE.finditer(text):
            try:
                if match.group(1):
                    parsed = date(
                        int(match.group(1)),
                        int(match.group(2)),
                        int(match.group(3)),
                    )
                else:
                    year = int(match.group(6))
                    if year < 100:
                        year += 2000
                    parsed = date(
                        year,
                        int(match.group(5)),
                        int(match.group(4)),
                    )
            except ValueError:
                continue

            if parsed not in results:
                results.append(parsed)
        return results

    @classmethod
    def _extract_identifier(cls, original: str, action_terms: tuple[str, ...]) -> str:
        lowered = original.lower()
        working = original
        for term in action_terms:
            idx = lowered.find(term)
            if idx == 0:
                working = original[len(term):]
                break
        first_date = DATE_RE.search(working)
        if first_date:
            working = working[:first_date.start()]

        working = re.sub(
            r"\b(propiedad|propiedades|alojamiento|alojamientos|habitacion|habitación|habitaciones|unidad|unidades|de|del|para|ver|las|los|proximas|próximas|futuras)\b",
            " ",
            working,
            flags=re.IGNORECASE,
        )
        working = re.sub(r"\s+", " ", working).strip(" ,.-")
        return working.strip()


class AccommodationCommandProcessor:
    """End-to-end processor for accommodation group commands."""

    @staticmethod
    def process_and_reply(message_content: str, chat_id: str, sender_phone: str = "") -> bool:
        parsed = AccommodationCommandParser.parse(message_content or "")
        if not parsed:
            return False

        group_chat = WhatsAppChat.objects.filter(chat_id=chat_id, type="group", is_active=True).first()
        if not group_chat:
            return False

        accommodations = list(AccommodationCommandProcessor._get_accessible_accommodations(group_chat))
        if not accommodations:
            return False

        if not AccommodationCommandProcessor._is_sender_authorized(group_chat, accommodations, sender_phone):
            reply = (
                "No puedo ejecutar ese comando desde este número. "
                "Configura el teléfono del operador en Tuki o usa un número autorizado."
            )
            return AccommodationCommandProcessor._send_reply(chat_id, reply)

        reply = AccommodationCommandProcessor._execute(parsed, accommodations)
        return AccommodationCommandProcessor._send_reply(chat_id, reply)

    @staticmethod
    def _get_accessible_accommodations(group_chat: WhatsAppChat):
        operator_ids = set(
            TourOperator.objects.filter(default_whatsapp_group=group_chat, is_active=True).values_list("id", flat=True)
        )
        if group_chat.assigned_operator_id:
            operator_ids.add(group_chat.assigned_operator_id)
        operator_ids.update(
            AccommodationGroupBinding.objects.filter(
                whatsapp_group=group_chat,
                is_active=True,
                tour_operator_id__isnull=False,
            ).values_list("tour_operator_id", flat=True)
        )

        filters = (
            Q(whatsapp_group_bindings__whatsapp_group=group_chat, whatsapp_group_bindings__is_active=True)
            | Q(hotel__default_whatsapp_group=group_chat)
            | Q(rental_hub__default_whatsapp_group=group_chat)
        )
        if operator_ids:
            filters |= Q(operator_bindings__tour_operator_id__in=operator_ids, operator_bindings__is_active=True)

        return (
            Accommodation.objects.filter(deleted_at__isnull=True)
            .filter(filters)
            .select_related("hotel", "rental_hub", "organizer")
            .distinct()
            .order_by("title", "unit_number", "slug")
        )

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        return "".join(ch for ch in str(phone or "") if ch.isdigit())

    @staticmethod
    def _is_sender_authorized(group_chat: WhatsAppChat, accommodations: Iterable[Accommodation], sender_phone: str) -> bool:
        normalized_sender = AccommodationCommandProcessor._normalize_phone(sender_phone)
        if not normalized_sender:
            return True

        operator_ids = set()
        if group_chat.assigned_operator_id:
            operator_ids.add(group_chat.assigned_operator_id)
        operator_ids.update(
            TourOperator.objects.filter(default_whatsapp_group=group_chat, is_active=True).values_list("id", flat=True)
        )
        operator_ids.update(
            AccommodationGroupBinding.objects.filter(
                whatsapp_group=group_chat,
                is_active=True,
                tour_operator_id__isnull=False,
            ).values_list("tour_operator_id", flat=True)
        )
        for accommodation in accommodations:
            operator_ids.update(
                accommodation.operator_bindings.filter(is_active=True).values_list("tour_operator_id", flat=True)
            )

        operators = TourOperator.objects.filter(id__in=operator_ids, is_active=True)
        configured_phones = {
            AccommodationCommandProcessor._normalize_phone(op.whatsapp_number or op.contact_phone)
            for op in operators
            if AccommodationCommandProcessor._normalize_phone(op.whatsapp_number or op.contact_phone)
        }
        if not configured_phones:
            return True
        return normalized_sender in configured_phones

    @staticmethod
    def _execute(parsed: ParsedAccommodationCommand, accommodations: list[Accommodation]) -> str:
        if parsed.action == "list":
            return AccommodationCommandProcessor._render_list(accommodations)

        target, error = AccommodationCommandProcessor._resolve_accommodation(parsed.identifier, accommodations)
        if error:
            return error

        if parsed.action in {"block", "unblock"}:
            if not parsed.start_date:
                return (
                    "Falta la fecha. Usa por ejemplo: "
                    "`Tuki bloquear 5 2026-03-20` o `Tuki liberar 5 2026-03-20 a 2026-03-25`."
                )
            return AccommodationCommandProcessor._apply_block_change(
                accommodation=target,
                start_date=parsed.start_date,
                end_date=parsed.end_date or parsed.start_date,
                unblock=parsed.action == "unblock",
            )

        if parsed.action == "availability":
            start_date = parsed.start_date or timezone.localdate()
            end_date = parsed.end_date or start_date
            return AccommodationCommandProcessor._render_availability(target, start_date, end_date)

        if parsed.action == "reservations":
            start_date = parsed.start_date or timezone.localdate()
            end_date = parsed.end_date
            return AccommodationCommandProcessor._render_reservations(target, start_date, end_date)

        return "Comando no reconocido."

    @staticmethod
    def _extract_slug_from_identifier(identifier: str) -> str:
        if not identifier:
            return ""
        if "://" not in identifier:
            return ""
        parsed = urlparse(identifier.strip())
        if not parsed.path:
            return ""
        match = LINK_SLUG_RE.search(parsed.path)
        if match:
            return match.group(1).strip().lower()
        return parsed.path.rstrip("/").split("/")[-1].strip().lower()

    @staticmethod
    def _resolve_accommodation(identifier: str, accommodations: list[Accommodation]) -> tuple[Optional[Accommodation], Optional[str]]:
        if not identifier:
            return None, (
                "Falta la propiedad. Primero usa `Tuki propiedades` y luego referencia una con su número, "
                "slug, external_id, número de unidad o link."
            )

        cleaned = identifier.strip()
        if cleaned.startswith("#"):
            cleaned = cleaned[1:].strip()

        if cleaned.isdigit():
            index = int(cleaned)
            if 1 <= index <= len(accommodations):
                return accommodations[index - 1], None
            return None, f"No existe la propiedad #{index} en este grupo."

        normalized = cleaned.lower()
        link_slug = AccommodationCommandProcessor._extract_slug_from_identifier(cleaned)

        exact_matches = []
        partial_matches = []
        for acc in accommodations:
            candidates = {
                (acc.slug or "").lower(),
                (acc.external_id or "").lower(),
                (acc.unit_number or "").lower(),
                (acc.room_type_code or "").lower(),
                (acc.title or "").lower(),
            }
            title_normalized = re.sub(r"\s+", " ", (acc.title or "").lower()).strip()
            exact_hit = normalized in candidates or (link_slug and link_slug == (acc.slug or "").lower())
            partial_hit = (
                normalized in title_normalized
                or normalized in (acc.slug or "").lower()
                or normalized in (acc.external_id or "").lower()
            )
            if exact_hit:
                exact_matches.append(acc)
            elif partial_hit:
                partial_matches.append(acc)

        matches = exact_matches or partial_matches
        if not matches:
            return None, (
                f"No encontré una propiedad que coincida con `{identifier}`. "
                "Usa `Tuki propiedades` para ver las referencias válidas."
            )
        if len(matches) > 1:
            options = "\n".join(
                AccommodationCommandProcessor._format_accommodation_line(acc, idx)
                for idx, acc in enumerate(accommodations, start=1)
                if acc in matches[:8]
            )
            return None, (
                f"`{identifier}` es ambiguo. Usa el número de la lista o un identificador más preciso.\n{options}"
            )
        return matches[0], None

    @staticmethod
    def _format_accommodation_line(accommodation: Accommodation, index: int) -> str:
        parts = [f"#{index} {accommodation.title}"]
        if accommodation.unit_number:
            parts.append(f"unidad {accommodation.unit_number}")
        if accommodation.external_id:
            parts.append(f"ext {accommodation.external_id}")
        if accommodation.hotel_id and accommodation.hotel:
            parts.append(f"hotel {accommodation.hotel.name}")
        if accommodation.rental_hub_id and accommodation.rental_hub:
            parts.append(f"central {accommodation.rental_hub.name}")
        parts.append(f"slug {accommodation.slug}")
        return " | ".join(parts)

    @staticmethod
    def _render_list(accommodations: list[Accommodation]) -> str:
        lines = ["Propiedades disponibles en este grupo:"]
        for idx, accommodation in enumerate(accommodations, start=1):
            lines.append(AccommodationCommandProcessor._format_accommodation_line(accommodation, idx))
        lines.append("")
        lines.append("Ejemplos:")
        lines.append("`Tuki bloquear 5 2026-03-20 a 2026-03-25`")
        lines.append("`Tuki disponibilidad mi-slug 2026-03-20`")
        lines.append("`Tuki reservas 5`")
        return "\n".join(lines[:60])

    @staticmethod
    def _date_range(start_date: date, end_date: date) -> list[date]:
        current = start_date
        days = []
        while current <= end_date:
            days.append(current)
            current += timedelta(days=1)
        return days

    @staticmethod
    def _apply_block_change(accommodation: Accommodation, start_date: date, end_date: date, unblock: bool) -> str:
        if end_date < start_date:
            return "`date_to` debe ser igual o posterior a la fecha inicial."

        days = AccommodationCommandProcessor._date_range(start_date, end_date)
        if unblock:
            deleted, _ = AccommodationBlockedDate.objects.filter(
                accommodation=accommodation,
                date__gte=start_date,
                date__lte=end_date,
            ).delete()
            verb = "liberadas"
            count = deleted
        else:
            count = 0
            for day in days:
                _, created = AccommodationBlockedDate.objects.get_or_create(
                    accommodation=accommodation,
                    date=day,
                )
                if created:
                    count += 1
            verb = "bloqueadas"

        if start_date == end_date:
            return f"✅ {accommodation.title}: {count} fecha {verb} ({start_date.isoformat()})."
        return (
            f"✅ {accommodation.title}: {count} fecha(s) {verb} "
            f"entre {start_date.isoformat()} y {end_date.isoformat()}."
        )

    @staticmethod
    def _get_day_status_map(accommodation: Accommodation, start_date: date, end_date: date) -> dict[date, str]:
        blocked_days = set(
            AccommodationBlockedDate.objects.filter(
                accommodation=accommodation,
                date__gte=start_date,
                date__lte=end_date,
            ).values_list("date", flat=True)
        )
        reservations = AccommodationReservation.objects.filter(
            accommodation=accommodation,
            status__in=("pending", "paid"),
            check_in__lt=end_date + timedelta(days=1),
            check_out__gt=start_date,
        ).order_by("check_in")

        status_map = {day: "libre" for day in AccommodationCommandProcessor._date_range(start_date, end_date)}
        for day in blocked_days:
            status_map[day] = "bloqueado"
        for reservation in reservations:
            cursor = max(start_date, reservation.check_in)
            reservation_end = min(end_date, reservation.check_out - timedelta(days=1))
            while cursor <= reservation_end:
                status_map[cursor] = "reservado"
                cursor += timedelta(days=1)
        return status_map

    @staticmethod
    def _render_availability(accommodation: Accommodation, start_date: date, end_date: date) -> str:
        if end_date < start_date:
            return "La fecha final debe ser igual o posterior a la inicial."

        status_map = AccommodationCommandProcessor._get_day_status_map(accommodation, start_date, end_date)
        lines = [f"Disponibilidad de {accommodation.title}:"]

        if len(status_map) <= 21:
            for day, status in status_map.items():
                lines.append(f"- {day.isoformat()}: {status}")
        else:
            counts = {"libre": 0, "bloqueado": 0, "reservado": 0}
            for status in status_map.values():
                counts[status] = counts.get(status, 0) + 1
            lines.append(
                f"Rango {start_date.isoformat()} -> {end_date.isoformat()}: "
                f"{counts['libre']} libre(s), {counts['bloqueado']} bloqueado(s), {counts['reservado']} reservado(s)."
            )
            conflicts = [f"- {day.isoformat()}: {status}" for day, status in status_map.items() if status != "libre"][:12]
            if conflicts:
                lines.append("Fechas ocupadas o bloqueadas:")
                lines.extend(conflicts)

        return "\n".join(lines)

    @staticmethod
    def _render_reservations(accommodation: Accommodation, start_date: date, end_date: Optional[date]) -> str:
        qs = AccommodationReservation.objects.filter(
            accommodation=accommodation,
            status__in=("pending", "paid"),
            check_out__gte=start_date,
        ).order_by("check_in", "created_at")

        if end_date:
            if end_date < start_date:
                return "La fecha final debe ser igual o posterior a la inicial."
            qs = qs.filter(check_in__lte=end_date)

        reservations = list(qs[:20])
        title = f"Reservas futuras de {accommodation.title}:"
        if not reservations:
            return f"{title}\n- No hay reservas futuras."

        lines = [title]
        for reservation in reservations:
            guest_name = f"{reservation.first_name} {reservation.last_name}".strip() or reservation.email or "Sin nombre"
            lines.append(
                f"- {reservation.reservation_id} | {reservation.check_in.isoformat()} -> "
                f"{reservation.check_out.isoformat()} | {reservation.status} | "
                f"{guest_name} | {reservation.guests} huésped(es)"
            )
        return "\n".join(lines)

    @staticmethod
    def _send_reply(chat_id: str, reply: str) -> bool:
        try:
            service = WhatsAppWebService()
            service.send_message("", reply, group_id=chat_id)
            logger.info("Accommodation command replied in group %s", chat_id)
            return True
        except Exception as exc:
            logger.exception("Failed to send accommodation command reply: %s", exc)
            return False
