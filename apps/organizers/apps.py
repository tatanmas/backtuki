"""App configuration for the organizers app."""

from django.apps import AppConfig


class OrganizersConfig(AppConfig):
    """Configuration for the organizers app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.organizers'
    
    def ready(self):
        """Initialize app when ready."""
        import apps.organizers.signals  # noqa 