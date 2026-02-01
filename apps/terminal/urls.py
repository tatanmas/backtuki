"""URLs for terminal API."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TerminalCompanyViewSet,
    TerminalRouteViewSet,
    TerminalTripViewSet,
    TerminalExcelUploadViewSet,
    TerminalDestinationViewSet,
    TerminalAdvertisingSpaceViewSet,
    TerminalDestinationExperienceConfigViewSet,
    PublicAdvertisingSpacesView,
    PublicDestinationExperiencesView,
)

router = DefaultRouter()
router.register(r'companies', TerminalCompanyViewSet, basename='terminal-company')
router.register(r'routes', TerminalRouteViewSet, basename='terminal-route')
router.register(r'trips', TerminalTripViewSet, basename='terminal-trip')
router.register(r'uploads', TerminalExcelUploadViewSet, basename='terminal-upload')
router.register(r'destinations', TerminalDestinationViewSet, basename='terminal-destination')
router.register(r'advertising-spaces', TerminalAdvertisingSpaceViewSet, basename='terminal-advertising-space')
router.register(r'destination-experiences', TerminalDestinationExperienceConfigViewSet, basename='terminal-destination-experience')

urlpatterns = [
    path('', include(router.urls)),
    # Public endpoints (no authentication required)
    path('public/advertising-spaces/', PublicAdvertisingSpacesView.as_view(), name='public-advertising-spaces'),
    path('public/destinations/<str:slug>/experiences/', PublicDestinationExperiencesView.as_view(), name='public-destination-experiences'),
]

