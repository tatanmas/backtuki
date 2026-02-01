"""WhatsApp app configuration."""
from django.apps import AppConfig


class WhatsAppConfig(AppConfig):
    """Configuration for WhatsApp app."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.whatsapp'
    verbose_name = 'WhatsApp Integration'

