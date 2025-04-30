"""App configuration for the users app."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Configuration for the users app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    
    def ready(self):
        """Initialize app when ready."""
        import apps.users.signals  # noqa 