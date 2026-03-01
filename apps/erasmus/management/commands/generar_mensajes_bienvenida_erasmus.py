"""
Genera mensajes de bienvenida Erasmus para enviar manualmente por WhatsApp.

Útil cuando el bot no pudo responder (ej. deploy largo, WhatsApp desconectado):
pasas los códigos ERAS-XXXXX de quienes escribieron y obtienes el texto
personalizado para cada uno (y el link de acceso se genera/guarda para que funcione).

Uso por SSH en el servidor (superadmin / backend):

  # Códigos como argumentos
  python manage.py generar_mensajes_bienvenida_erasmus ERAS-abc123 ERAS-def456

  # Códigos desde archivo (un código por línea)
  python manage.py generar_mensajes_bienvenida_erasmus --from-file codigos.txt

  # Guardar salida en archivo
  python manage.py generar_mensajes_bienvenida_erasmus --from-file codigos.txt -o mensajes.txt

Con Docker (tuki-backend):
  docker compose run --rm tuki-backend python manage.py generar_mensajes_bienvenida_erasmus ERAS-abc123
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.erasmus.access_code_service import (
    LINK_EXPIRY_HOURS,
    get_welcome_message_text,
)
from apps.erasmus.models import ErasmusMagicLink


def _normalize_code(raw: str) -> str:
    """ERAS-abc123 -> ERAS-ABC123."""
    s = (raw or "").strip().upper()
    if s and not s.startswith("ERAS-"):
        s = "ERAS-" + s
    return s


def _ensure_magic_link_token(magic: ErasmusMagicLink) -> str:
    """
    If the magic link has no access_token yet (e.g. user wrote during deploy),
    generate and save it so the link will work when they receive the message.
    Returns the access_token (existing or new).
    """
    if magic.access_token:
        return magic.access_token
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    magic.access_token = token
    magic.status = ErasmusMagicLink.STATUS_LINK_SENT
    magic.link_expires_at = now + timedelta(hours=LINK_EXPIRY_HOURS)
    magic.save(update_fields=["access_token", "status", "link_expires_at", "updated_at"])
    return token


def _format_output(code: str, phone: str, first_name: str, message: str) -> str:
    """Single block for one lead, easy to copy into WhatsApp."""
    lines = [
        "",
        "=" * 60,
        f"Código: {code}  |  Tel: {phone or '(sin teléfono)'}  |  Nombre: {first_name}",
        "-" * 60,
        message.strip(),
        "=" * 60,
    ]
    return "\n".join(lines)


class Command(BaseCommand):
    help = "Genera mensajes de bienvenida Erasmus por código ERAS-XXXXX para enviar manualmente por WhatsApp"

    def add_arguments(self, parser):
        parser.add_argument(
            "codes",
            nargs="*",
            type=str,
            help="Códigos ERAS-XXXXX (ej. ERAS-abc123 ERAS-def456)",
        )
        parser.add_argument(
            "--from-file",
            "-f",
            type=str,
            metavar="PATH",
            help="Archivo con un código por línea (ignora códigos en args)",
        )
        parser.add_argument(
            "-o", "--output",
            type=str,
            metavar="PATH",
            help="Archivo donde escribir la salida (por defecto stdout)",
        )

    def handle(self, *args, **options):
        codes = list(options.get("codes") or [])
        from_file = options.get("from_file")
        output_path = options.get("output")

        if from_file:
            try:
                with open(from_file, "r", encoding="utf-8") as f:
                    codes = [line.strip() for line in f if line.strip()]
            except FileNotFoundError:
                self.stderr.write(self.style.ERROR(f"Archivo no encontrado: {from_file}"))
                return
            except OSError as e:
                self.stderr.write(self.style.ERROR(f"No se pudo leer {from_file}: {e}"))
                return

        if not codes:
            self.stderr.write(
                self.style.ERROR(
                    "Indica códigos: como argumentos (ERAS-xxx ERAS-yyy) o --from-file archivo.txt"
                )
            )
            return

        frontend_url = (getattr(settings, "FRONTEND_URL", "http://localhost:8080") or "").rstrip("/")
        if not frontend_url:
            self.stderr.write(self.style.WARNING("FRONTEND_URL no configurado; el link puede ser incorrecto."))

        out_lines = []
        not_found = []
        for raw in codes:
            code = _normalize_code(raw)
            if not code:
                continue
            try:
                magic = ErasmusMagicLink.objects.select_related("lead").get(verification_code=code)
            except ErasmusMagicLink.DoesNotExist:
                not_found.append(code)
                continue

            lead = magic.lead
            token = _ensure_magic_link_token(magic)
            magic_link_url = f"{frontend_url}/erasmus/acceder?token={token}"
            message_text = get_welcome_message_text(lead, magic_link_url)

            phone = (lead.phone_country_code or "").replace(" ", "") + (lead.phone_number or "").replace(" ", "")
            if phone and not phone.startswith("+"):
                phone = "+" + phone
            first_name = (lead.first_name or "").strip() or "Erasmus"

            block = _format_output(code, phone or "", first_name, message_text)
            out_lines.append(block)

        if not_found:
            self.stderr.write(self.style.WARNING(f"Códigos no encontrados: {', '.join(not_found)}"))

        result = "\n".join(out_lines) if out_lines else "No se generó ningún mensaje."

        if output_path:
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(result)
                self.stdout.write(self.style.SUCCESS(f"Escrito en {output_path} ({len(out_lines)} mensaje(s))."))
            except OSError as e:
                self.stderr.write(self.style.ERROR(f"No se pudo escribir en {output_path}: {e}"))
        else:
            self.stdout.write(result)
