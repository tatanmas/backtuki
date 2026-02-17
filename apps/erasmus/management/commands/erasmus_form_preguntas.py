"""
Extrae la lista actual de preguntas del formulario Erasmus (campos fijos + preguntas extra en BD).
Sirve para saber qué preguntar por WhatsApp o qué falta al armar un lead desde una conversación.

Uso:
  python manage.py erasmus_form_preguntas
  python manage.py erasmus_form_preguntas --json
  python manage.py erasmus_form_preguntas -o carga/erasmus/preguntas_actuales.json
"""

import json
from django.core.management.base import BaseCommand

from apps.erasmus.models import ErasmusExtraField


# Campos fijos del modelo ErasmusLead con la pregunta sugerida para hacer por WhatsApp
CAMPOS_FIJOS = [
    {"key": "first_name", "pregunta": "¿Cuál es tu nombre?", "required": True, "type": "text"},
    {"key": "last_name", "pregunta": "¿Cuál es tu apellido?", "required": True, "type": "text"},
    {"key": "nickname", "pregunta": "¿Cómo te gustaría que te digamos? (apodo)", "required": False, "type": "text"},
    {"key": "birth_date", "pregunta": "¿Cuál es tu fecha de nacimiento? (ej. 2000-05-15)", "required": True, "type": "date"},
    {"key": "country", "pregunta": "¿De qué país eres?", "required": False, "type": "text"},
    {"key": "city", "pregunta": "¿De qué ciudad?", "required": False, "type": "text"},
    {"key": "email", "pregunta": "¿Cuál es tu email?", "required": False, "type": "email"},
    {"key": "phone_country_code", "pregunta": "¿Cuál es tu código de país del teléfono? (ej. +57)", "required": True, "type": "text"},
    {"key": "phone_number", "pregunta": "¿Cuál es tu número de teléfono (sin código de país)?", "required": True, "type": "text"},
    {"key": "instagram", "pregunta": "¿Tu Instagram? (opcional)", "required": False, "type": "text"},
    {"key": "stay_reason", "pregunta": "¿Vienes por intercambio/universidad, prácticas/internship u otro?", "required": True, "type": "choice", "choices": ["university", "practicas", "other"]},
    {"key": "stay_reason_detail", "pregunta": "Si es prácticas u otro: ¿dónde o qué harás?", "required": False, "type": "text"},
    {"key": "university", "pregunta": "¿En qué universidad vas a estudiar? (si es intercambio)", "required": "si stay_reason=university", "type": "text"},
    {"key": "degree", "pregunta": "¿Qué carrera o programa?", "required": "si stay_reason=university", "type": "text"},
    {"key": "arrival_date", "pregunta": "¿Cuándo llegas a Chile? (fecha, ej. 2026-02-22)", "required": True, "type": "date"},
    {"key": "departure_date", "pregunta": "¿Hasta cuándo te quedas? (fecha, ej. 2026-07-12)", "required": True, "type": "date"},
    {"key": "has_accommodation_in_chile", "pregunta": "¿Ya tienes alojamiento en Chile?", "required": False, "type": "boolean"},
    {"key": "wants_rumi4students_contact", "pregunta": "¿Quieres que te contactemos para ayudarte a encontrar alojamiento? (Rumi4Students u otros)", "required": False, "type": "boolean"},
    {"key": "destinations", "pregunta": "¿Qué destinos te interesan? (ej. san-pedro-atacama, valparaiso)", "required": False, "type": "list"},
    {"key": "interests", "pregunta": "¿Qué te interesa? (ej. trekking, surf, naturaleza)", "required": False, "type": "list"},
    {"key": "source_slug", "pregunta": "(interno) Origen del lead, ej. whatsapp", "required": False, "type": "text"},
    {"key": "extra_data", "pregunta": "Respuestas a preguntas dinámicas (ver listado abajo)", "required": False, "type": "object"},
]

# Consent: no se preguntan por WhatsApp normalmente; en carga manual se ponen en false
CONSENT_KEYS = [
    "accept_tc_erasmus",
    "accept_privacy_erasmus",
    "consent_email",
    "consent_whatsapp",
    "consent_share_providers",
]


class Command(BaseCommand):
    help = "Lista las preguntas del formulario Erasmus (campos fijos + extra desde BD) para saber qué preguntar por WhatsApp"

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Salida en JSON (lista de objetos con key, pregunta, required, type)",
        )
        parser.add_argument(
            "-o", "--output",
            type=str,
            help="Ruta de archivo donde escribir la salida (JSON o texto según --json)",
        )

    def handle(self, *args, **options):
        out_json = options.get("json", False)
        output_path = options.get("output")

        # Campos fijos
        items = list(CAMPOS_FIJOS)

        # Consent (solo referencia, no se preguntan por chat)
        for key in CONSENT_KEYS:
            items.append({
                "key": key,
                "pregunta": f"(Consentimiento: no preguntar por WhatsApp; en carga usar false si no aplica)",
                "required": False,
                "type": "boolean",
            })

        # Preguntas dinámicas desde BD
        extra = list(
            ErasmusExtraField.objects.filter(is_active=True).order_by("order", "id").values(
                "field_key", "label", "type", "required", "help_text", "options"
            )
        )
        for e in extra:
            items.append({
                "key": e["field_key"],
                "pregunta": e["label"],
                "required": e["required"],
                "type": e["type"],
                "help_text": e["help_text"] or "",
                "options": e.get("options") or [],
                "source": "ErasmusExtraField (BD)",
            })

        if out_json or output_path:
            # Serializar para JSON (no incluir source en todos para mantener formato simple)
            export = []
            for it in items:
                row = {"key": it["key"], "pregunta": it["pregunta"], "required": it["required"], "type": it["type"]}
                if it.get("choices"):
                    row["choices"] = it["choices"]
                if it.get("help_text"):
                    row["help_text"] = it["help_text"]
                if it.get("options"):
                    row["options"] = it["options"]
                if it.get("source"):
                    row["source"] = it["source"]
                export.append(row)
            text = json.dumps(export, ensure_ascii=False, indent=2)
            if output_path:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.stdout.write(self.style.SUCCESS(f"Escrito en {output_path}"))
            else:
                self.stdout.write(text)
            return

        # Salida legible
        lines = [
            "PREGUNTAS FORMULARIO ERASMUS (para completar lead por WhatsApp)",
            "=" * 60,
            "",
            "CAMPOS FIJOS",
            "-" * 40,
        ]
        for it in items:
            if it.get("source") == "ErasmusExtraField (BD)":
                continue
            req = " [OBLIGATORIO]" if it["required"] is True else (" [si universidad]" if it["required"] == "si stay_reason=university" else "")
            lines.append(f"  {it['key']}{req}")
            lines.append(f"    → {it['pregunta']}")
            lines.append("")

        if extra:
            lines.append("PREGUNTAS DINÁMICAS (desde BD, Superadmin → Erasmus → Preguntas)")
            lines.append("-" * 40)
            for e in extra:
                req = " [OBLIGATORIO]" if e["required"] else ""
                lines.append(f"  {e['field_key']}{req}")
                lines.append(f"    → {e['label']}")
                if e.get("help_text"):
                    lines.append(f"    ({e['help_text']})")
                lines.append("")

        lines.append("")
        lines.append("Consent (accept_tc_erasmus, etc.): en carga por WhatsApp usar false si no aplica.")
        text = "\n".join(lines)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)
            self.stdout.write(self.style.SUCCESS(f"Escrito en {output_path}"))
        else:
            self.stdout.write(text)
