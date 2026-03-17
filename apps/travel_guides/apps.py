from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TravelGuidesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.travel_guides'
    verbose_name = _('Travel Guides')
