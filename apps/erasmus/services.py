"""Services for Erasmus: guides by destination, WhatsApp sending."""
import logging
from typing import List

from .models import ErasmusDestinationGuide, ErasmusLead

logger = logging.getLogger(__name__)


def get_guides_for_destinations(destination_slugs: List[str]) -> List[dict]:
    """
    Return active guides for the given destination slugs.
    Each guide is dict with: id, destination_slug, title, description, file_url, order.
    """
    if not destination_slugs:
        return []
    guides = ErasmusDestinationGuide.objects.filter(
        destination_slug__in=destination_slugs,
        is_active=True,
    ).order_by("destination_slug", "order", "id")
    return [
        {
            "id": g.id,
            "destination_slug": g.destination_slug,
            "title": g.title,
            "description": g.description or "",
            "file_url": g.file_url or "",
            "order": g.order,
        }
        for g in guides
    ]


def send_erasmus_guides_whatsapp(lead: ErasmusLead) -> None:
    """
    Send the lead a WhatsApp message with their travel guides (by destination).
    Uses lead.phone_country_code + lead.phone_number. No-op if no guides or no phone.
    """
    destinations = list(lead.destinations or [])
    if not destinations:
        return
    guides = get_guides_for_destinations(destinations)
    if not guides:
        logger.info("[Erasmus] No guides configured for destinations %s", destinations)
        return

    phone = (lead.phone_country_code or "").replace(" ", "") + (lead.phone_number or "").replace(" ", "")
    if len(phone) < 10:
        logger.warning("[Erasmus] Lead %s has no valid phone for WhatsApp", lead.id)
        return

    from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
    service = WhatsAppWebService()
    clean_phone = service.clean_phone_number(phone)
    if not clean_phone.startswith("56") and len(clean_phone) >= 9:
        clean_phone = "56" + clean_phone.lstrip("0")

    name = (lead.first_name or "").strip() or "Erasmus"
    lines = [
        f"¡Hola {name}! 👋",
        "",
        "Según los destinos que elegiste, aquí tienes tus *guías de viaje*:",
        "",
    ]
    current_slug = None
    for g in guides:
        if g["destination_slug"] != current_slug:
            current_slug = g["destination_slug"]
            lines.append(f"📍 *{current_slug.replace('-', ' ').title()}*")
        line = f"• {g['title']}"
        if g.get("file_url"):
            line += f" → {g['file_url']}"
        lines.append(line)
    lines.extend([
        "",
        "También las tienes guardadas en tu perfil en tuki.cl cuando inicies sesión.",
        "",
        "¡Que tengas un Erasmus increíble! 🎒",
    ])
    message = "\n".join(lines)

    try:
        service.send_message(clean_phone, message)
        logger.info("[Erasmus] Sent %s guides by WhatsApp to lead %s", len(guides), lead.id)
    except Exception as e:
        logger.exception("[Erasmus] Failed to send WhatsApp guides to lead %s: %s", lead.id, e)
