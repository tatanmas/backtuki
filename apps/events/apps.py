"""App configuration for the events app."""

from django.apps import AppConfig


class EventsConfig(AppConfig):
    """Configuration for the events app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.events'
    
    def ready(self):
        """Initialize app when ready."""
        import apps.events.signals  # noqa 