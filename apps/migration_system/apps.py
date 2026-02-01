"""App configuration for migration_system."""

from django.apps import AppConfig


class MigrationSystemConfig(AppConfig):
    """Configuration for the migration system app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.migration_system'
    verbose_name = 'Migration System'
    
    def ready(self):
        """Import signals when app is ready."""
        # Import signals here if needed
        pass
