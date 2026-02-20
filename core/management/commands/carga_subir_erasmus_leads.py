"""
Importar leads Erasmus desde un JSON (leads.json o payload.json con clave "leads").
Pensado para ejecutarse dentro del contenedor en Dako: sin tokens.
No crea User ni envía guías por WhatsApp por defecto; opción --send-guides para enviar.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.erasmus.models import ErasmusLead
from apps.erasmus.lead_import import (
    normalize_lead,
    REQUIRED_KEYS_FULL,
    REQUIRED_KEYS_INCOMPLETE,
)


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
        parser.add_argument(
            "--allow-incomplete",
            action="store_true",
            help="Permitir datos parciales: crear lead con nombre, teléfono, país, etc. aunque falten fechas o motivo; se marca como 'Por completar'",
        )

    def handle(self, *args, **options):
        path = Path(options["path"]).resolve()
        dry_run = options.get("dry_run", False)
        send_guides = options.get("send_guides", False)
        skip_duplicates = options.get("skip_duplicates", False)
        allow_incomplete = options.get("allow_incomplete", False)

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
                if allow_incomplete:
                    required = REQUIRED_KEYS_INCOMPLETE
                else:
                    required = REQUIRED_KEYS_FULL
                for key in required:
                    if not raw.get(key):
                        raise ValueError(f"Falta campo obligatorio: {key}")
                normalized = normalize_lead(raw, allow_incomplete=allow_incomplete)
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
