from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LandingDestinationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.landing_destinations'
    verbose_name = _('Landing Destinations')
