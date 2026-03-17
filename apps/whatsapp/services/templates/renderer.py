"""Template renderer for WhatsApp messages."""
import re
import logging
from typing import Dict, Any, Optional

from .defaults import DEFAULT_TEMPLATES
from .context import ContextBuilder

logger = logging.getLogger(__name__)


def _get_template_from_entity_templates(entity, message_type: str) -> Optional[str]:
    """Return template for message_type from an entity's whatsapp_message_templates dict if set."""
    if not entity:
        return None
    overrides = getattr(entity, 'whatsapp_message_templates', None) or {}
    if not isinstance(overrides, dict):
        return None
    custom = (overrides or {}).get(message_type)
    if custom and (custom or '').strip():
        return (custom or '').strip()
    return None


def _get_template_for_reservation(reservation, message_type: str) -> str:
    """
    Resolve template in order:
    - Experience: experience override -> platform -> operator -> default.
    - Accommodation: accommodation -> hotel or rental_hub -> platform -> operator -> default.
    - Car: car override -> platform -> operator -> default (future).
    """
    # 1) Experience override (if reservation has experience)
    experience = getattr(reservation, 'experience', None)
    if experience:
        custom = _get_template_from_entity_templates(experience, message_type)
        if custom:
            return custom

    # 2) Accommodation 3-layer: room -> hotel or central -> then fall through to platform
    accommodation = getattr(reservation, 'accommodation', None)
    if accommodation:
        custom = _get_template_from_entity_templates(accommodation, message_type)
        if custom:
            return custom
        if getattr(accommodation, 'hotel_id', None) and accommodation.hotel:
            custom = _get_template_from_entity_templates(accommodation.hotel, message_type)
            if custom:
                return custom
        if getattr(accommodation, 'rental_hub_id', None) and accommodation.rental_hub:
            custom = _get_template_from_entity_templates(accommodation.rental_hub, message_type)
            if custom:
                return custom

    # 3) Platform global config (singleton)
    try:
        from apps.whatsapp.models import WhatsAppReservationMessageConfig
        config = WhatsAppReservationMessageConfig.objects.filter(
            config_key=WhatsAppReservationMessageConfig.CONFIG_KEY
        ).first()
        if config and config.templates:
            custom = (config.templates or {}).get(message_type)
            if custom and (custom or '').strip():
                return (custom or '').strip()
    except Exception as e:
        logger.warning("Failed to load WhatsAppReservationMessageConfig: %s", e)

    # 4) Operator-specific template
    operator = getattr(reservation, 'operator', None)
    if operator:
        try:
            from apps.whatsapp.models import OperatorMessageTemplate
            t = OperatorMessageTemplate.objects.filter(
                operator=operator,
                message_type=message_type,
                is_active=True
            ).first()
            if t and (t.template or '').strip():
                return (t.template or '').strip()
        except Exception:
            pass

    # 5) Hardcoded default
    return DEFAULT_TEMPLATES.get(message_type, '')


class TemplateRenderer:
    """Renders message templates with context variables."""

    @staticmethod
    def get_template(operator, message_type: str) -> str:
        """Get template for operator only (legacy). Prefer get_template_for_reservation."""
        try:
            from apps.whatsapp.models import OperatorMessageTemplate
            template = OperatorMessageTemplate.objects.get(
                operator=operator,
                message_type=message_type,
                is_active=True
            )
            return template.template
        except Exception:
            return DEFAULT_TEMPLATES.get(message_type, '')

    @staticmethod
    def render(template: str, context: Dict[str, Any]) -> str:
        """Replace variables in template with context values."""
        result = template
        for key, value in context.items():
            result = result.replace(f"{{{{{key}}}}}", str(value) if value else '')
        # Clean unreplaced variables
        result = re.sub(r'\{\{[^}]+\}\}', '', result)
        return result.strip()

    @classmethod
    def render_message(
        cls,
        operator,
        message_type: str,
        reservation,
        code_obj=None,
        payment_link: Optional[str] = None
    ) -> str:
        """Render complete message using hierarchy: experience -> platform -> operator -> default."""
        template = _get_template_for_reservation(reservation, message_type)
        context = ContextBuilder.build(reservation, code_obj, payment_link)
        return cls.render(template, context)
