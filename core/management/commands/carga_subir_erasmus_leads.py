"""
Importar leads Erasmus desde un JSON (leads.json o payload.json con clave "leads").
Pensado para ejecutarse dentro del contenedor en Dako: sin tokens.
No crea User ni envía guías por WhatsApp por defecto; opción --send-guides para enviar.
"""

import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from apps.erasmus.models import ErasmusLead, ErasmusExtraField


# Default birth_date when missing (e.g. leads from WhatsApp without that info)
DEFAULT_BIRTH_DATE = date(2000, 1, 1)

REQUIRED_KEYS = (
    "first_name",
    "last_name",
    "phone_country_code",
    "phone_number",
    "stay_reason",
    "arrival_date",
    "departure_date",
)


def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parsed = parse_date(value)
        if parsed is None and value.strip():
            raise ValueError(f"Fecha inválida: {value!r}")
        return parsed or None
    return None


def _normalize_lead(raw: dict) -> dict:
    """Build a dict suitable for ErasmusLead with defaults for missing fields."""
    birth = _parse_date(raw.get("birth_date"))
    arrival = _parse_date(raw.get("arrival_date"))
    departure = _parse_date(raw.get("departure_date"))

    if not birth:
        birth = DEFAULT_BIRTH_DATE
    if not arrival:
        raise ValueError("arrival_date es obligatorio")
    if not departure:
        raise ValueError("departure_date es obligatorio")
    if departure < arrival:
        raise ValueError("departure_date debe ser posterior a arrival_date")

    stay_reason = (raw.get("stay_reason") or "").strip().lower()
    if stay_reason not in ("university", "practicas", "other"):
        raise ValueError("stay_reason debe ser university, practicas u other")

    extra_data = raw.get("extra_data")
    if not isinstance(extra_data, dict):
        extra_data = {}
    # Optionally restrict to active ErasmusExtraField keys (like the web serializer)
    active_extra_keys = set(
        ErasmusExtraField.objects.filter(is_active=True).values_list("field_key", flat=True)
    )
    if active_extra_keys:
        extra_data = {k: v for k, v in extra_data.items() if k in active_extra_keys}

    email = (raw.get("email") or "").strip() or None
    source_slug = (raw.get("source_slug") or "").strip() or None

    return {
        "first_name": (raw.get("first_name") or "").strip()[:150],
        "last_name": (raw.get("last_name") or "").strip()[:150],
        "nickname": (raw.get("nickname") or "").strip()[:100],
        "birth_date": birth,
        "country": (raw.get("country") or "").strip()[:100],
        "city": (raw.get("city") or "").strip()[:150],
        "email": email,
        "phone_country_code": (raw.get("phone_country_code") or "").strip()[:10],
        "phone_number": (raw.get("phone_number") or "").strip()[:20],
        "instagram": (raw.get("instagram") or "").strip()[:100],
        "stay_reason": stay_reason,
        "stay_reason_detail": (raw.get("stay_reason_detail") or "").strip()[:500],
        "university": (raw.get("university") or "").strip()[:255],
        "degree": (raw.get("degree") or "").strip()[:255],
        "arrival_date": arrival,
        "departure_date": departure,
        "has_accommodation_in_chile": bool(raw.get("has_accommodation_in_chile", False)),
        "wants_rumi4students_contact": bool(raw.get("wants_rumi4students_contact", False)),
        "destinations": [str(x)[:100] for x in (raw.get("destinations") or []) if isinstance(raw.get("destinations"), list)],
        "interests": [str(x)[:100] for x in (raw.get("interests") or []) if isinstance(raw.get("interests"), list)],
        "source_slug": source_slug,
        "utm_source": (raw.get("utm_source") or "").strip()[:255] or None,
        "utm_medium": (raw.get("utm_medium") or "").strip()[:255] or None,
        "utm_campaign": (raw.get("utm_campaign") or "").strip()[:255] or None,
        "extra_data": extra_data,
        "accept_tc_erasmus": bool(raw.get("accept_tc_erasmus", False)),
        "accept_privacy_erasmus": bool(raw.get("accept_privacy_erasmus", False)),
        "consent_email": bool(raw.get("consent_email", False)),
        "consent_whatsapp": bool(raw.get("consent_whatsapp", False)),
        "consent_share_providers": bool(raw.get("consent_share_providers", False)),
    }


class Command(BaseCommand):
    help = "Importa leads Erasmus desde leads.json (o payload.json con clave 'leads') en la carpeta indicada"

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=str,
            help="Ruta a la carpeta que contiene leads.json o payload.json",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo validar y listar lo que se crearía, sin escribir en BD",
        )
        parser.add_argument(
            "--send-guides",
            action="store_true",
            help="Enviar guías por WhatsApp a cada lead creado (por defecto no se envían)",
        )
        parser.add_argument(
            "--skip-duplicates",
            action="store_true",
            help="Si ya existe un lead con el mismo email o (email vacío y mismo teléfono), omitir en lugar de fallar",
        )

    def handle(self, *args, **options):
        path = Path(options["path"]).resolve()
        dry_run = options.get("dry_run", False)
        send_guides = options.get("send_guides", False)
        skip_duplicates = options.get("skip_duplicates", False)

        if not path.is_dir():
            self.stderr.write(self.style.ERROR(f"No es un directorio: {path}"))
            return

        leads_file = path / "leads.json"
        payload_file = path / "payload.json"
        if leads_file.exists():
            with open(leads_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                leads_data = data
            else:
                leads_data = data.get("leads") if isinstance(data, dict) else None
                if leads_data is None:
                    self.stderr.write(self.style.ERROR("leads.json debe ser un array o un objeto con clave 'leads'"))
                    return
        elif payload_file.exists():
            with open(payload_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                self.stderr.write(self.style.ERROR("payload.json debe ser un objeto con clave 'leads'"))
                return
            leads_data = data.get("leads")
            if leads_data is None:
                self.stderr.write(self.style.ERROR("payload.json debe tener clave 'leads' (array)"))
                return
            if not isinstance(leads_data, list):
                self.stderr.write(self.style.ERROR("payload.leads debe ser un array"))
                return
        else:
            self.stderr.write(self.style.ERROR(f"No existe {leads_file} ni {payload_file} en {path}"))
            return

        created = 0
        skipped_dup = 0
        errors = []

        for i, raw in enumerate(leads_data):
            if not isinstance(raw, dict):
                errors.append((i + 1, f"Ítem no es un objeto: {type(raw).__name__}"))
                continue
            try:
                for key in REQUIRED_KEYS:
                    if not raw.get(key):
                        raise ValueError(f"Falta campo obligatorio: {key}")
                normalized = _normalize_lead(raw)
            except Exception as e:
                errors.append((i + 1, str(e)))
                continue

            if skip_duplicates or dry_run:
                qs = ErasmusLead.objects.filter(
                    phone_country_code=normalized["phone_country_code"],
                    phone_number=normalized["phone_number"],
                )
                if qs.exists():
                    if dry_run:
                        self.stdout.write(f"  [dry-run] Omitiría duplicado: {normalized['first_name']} {normalized['last_name']}")
                    skipped_dup += 1
                    continue

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [dry-run] Crearía: {normalized['first_name']} {normalized['last_name']} "
                        f"({normalized['arrival_date']} - {normalized['departure_date']})"
                    )
                )
                created += 1
                continue

            lead = ErasmusLead.objects.create(**normalized)
            created += 1
            self.stdout.write(self.style.SUCCESS(f"  Creado: {lead.first_name} {lead.last_name} (id={lead.id})"))

            if send_guides:
                try:
                    from apps.erasmus.services import send_erasmus_guides_whatsapp
                    send_erasmus_guides_whatsapp(lead)
                    self.stdout.write("    Guías WhatsApp enviadas.")
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"    No se pudieron enviar guías: {e}"))

        if errors:
            self.stderr.write(self.style.ERROR(f"Errores en {len(errors)} ítem(s):"))
            for idx, msg in errors:
                self.stderr.write(self.style.ERROR(f"  Ítem {idx}: {msg}"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Total: {created} lead(s) creado(s)"
                + (f", {skipped_dup} duplicado(s) omitido(s)" if skipped_dup else "")
            )
        )
        if errors:
            raise SystemExit(1)
