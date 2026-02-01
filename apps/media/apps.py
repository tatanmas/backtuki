"""App configuration for media module."""

from django.apps import AppConfig


class MediaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.media'
    verbose_name = 'Media Library'

