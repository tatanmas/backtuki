"""
Contest participation code generation and WhatsApp reply.
Same robustness as reservation codes: unique code, flow, optional reply when message received.
"""
import hashlib
import secrets
import logging
from django.utils import timezone

from apps.erasmus.models import Contest, ContestRegistration, ContestParticipationCode
from core.flow_logger import FlowLogger

logger = logging.getLogger(__name__)

CODE_PREFIX = "CONC-"
MAX_RETRIES = 10


def generate_contest_code(contest: Contest) -> str:
    """Generate a unique code like CONC-ABC12DEF-20260316."""
    date_str = timezone.now().strftime("%Y%m%d")
    slug_prefix = (contest.slug[:6] if contest.slug else "CONC").upper().replace("-", "")
    for _ in range(MAX_RETRIES):
        unique_id = secrets.token_urlsafe(8).upper().replace("-", "").replace("_", "")[:8]
        hash_suffix = hashlib.sha256(
            f"{contest.id}-{unique_id}-{timezone.now().isoformat()}".encode()
        ).hexdigest()[:8].upper()
        code = f"{CODE_PREFIX}{slug_prefix}-{date_str}-{hash_suffix}"
        if not ContestParticipationCode.objects.filter(code=code).exists():
            return code
    raise ValueError("Could not generate unique contest code after multiple attempts")


def render_contest_whatsapp_message(contest: Contest, registration: ContestRegistration, code: str) -> str:
    """Render contest whatsapp_confirmation_message with placeholders."""
    template = (contest.whatsapp_confirmation_message or "").strip()
    if not template:
        return f"Hola {registration.first_name}, tu código de participación es: {code}. ¡Suerte!"
    name = f"{registration.first_name} {registration.last_name}".strip() or "Participante"
    return (
        template.replace("{{nombre}}", name)
        .replace("{{codigo}}", code)
        .replace("{{concurso}}", contest.title)
    )


def process_contest_code_from_whatsapp(message, code: str) -> bool:
    """
    Process an incoming WhatsApp message that contains a contest participation code.
    Sends the contest's personalized reply to the sender and marks the code as confirmed.
    Returns True if processed successfully, False otherwise.
    """
    from apps.whatsapp.models import WhatsAppMessage
    from apps.whatsapp.services.whatsapp_client import WhatsAppWebService

    try:
        code_obj = ContestParticipationCode.objects.select_related(
            "contest", "registration"
        ).get(code=code)
    except ContestParticipationCode.DoesNotExist:
        logger.warning("Contest code not found: %s", code)
        return False

    contest = code_obj.contest
    registration = code_obj.registration
    reply_text = render_contest_whatsapp_message(contest, registration, code)

    phone = WhatsAppWebService.clean_phone_number(message.phone)
    if not phone:
        logger.warning("Cannot send contest reply: no phone on message")
        return False

    try:
        WhatsAppWebService().send_message(phone, reply_text)
    except Exception as e:
        logger.exception("Failed to send contest confirmation to %s: %s", phone, e)
        return False

    code_obj.status = "confirmed"
    code_obj.save(update_fields=["status", "updated_at"])

    if code_obj.flow_id:
        flow = FlowLogger.from_flow_id(code_obj.flow_id)
        if flow:
            flow.log_event(
                "CONTEST_CODE_CONFIRMED_WHATSAPP",
                source="whatsapp",
                status="success",
                message="Participant sent code via WhatsApp; reply sent",
                metadata={"code": code},
            )

    logger.info("Contest code %s confirmed; reply sent to %s", code, phone)
    return True
