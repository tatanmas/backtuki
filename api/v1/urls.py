"""URL Configuration for API v1."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Import viewsets
from api.v1.users.views import UserViewSet
from api.v1.organizers.views import OrganizerViewSet, OrganizerOnboardingViewSet
from api.v1.events.views import (
    EventViewSet,
    EventCategoryViewSet,
    LocationViewSet,
    TicketTierViewSet,
)

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'organizers', OrganizerViewSet, basename='organizer')
router.register(r'organizer-onboarding', OrganizerOnboardingViewSet, basename='organizer-onboarding')
router.register(r'events', EventViewSet, basename='event')
router.register(r'event-categories', EventCategoryViewSet, basename='event-category')
router.register(r'locations', LocationViewSet, basename='location')
router.register(r'ticket-tiers', TicketTierViewSet, basename='ticket-tier')

# Wire up our API using automatic URL routing
urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('api.v1.auth.urls')),
] 