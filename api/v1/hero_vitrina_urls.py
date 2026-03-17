"""Public API URLs for hero vitrina (landing slider)."""

from django.urls import path
from .hero_vitrina_views import hero_vitrina_list

urlpatterns = [
    path('', hero_vitrina_list, name='hero-vitrina-list'),
]
