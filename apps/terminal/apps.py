"""Terminal app configuration."""

from django.apps import AppConfig


class TerminalConfig(AppConfig):
    """Configuration for terminal app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.terminal'
    verbose_name = 'Terminal'

