"""Template renderer for WhatsApp messages."""
import re
import logging
from typing import Dict, Any, Optional

from .defaults import DEFAULT_TEMPLATES
from .context import ContextBuilder

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """Renders message templates with context variables."""
    
    @staticmethod
    def get_template(operator, message_type: str) -> str:
        """Get template for operator, fallback to default."""
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
        """Render complete message for operator and type."""
        template = cls.get_template(operator, message_type)
        context = ContextBuilder.build(reservation, code_obj, payment_link)
        return cls.render(template, context)
