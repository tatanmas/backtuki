"""URLs for experiences API."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExperienceViewSet,
    TourLanguageViewSet,
    TourInstanceViewSet,
    TourBookingViewSet,
    OrganizerCreditViewSet
)

router = DefaultRouter()
router.register(r'experiences', ExperienceViewSet, basename='experience')
router.register(r'tour-languages', TourLanguageViewSet, basename='tour-language')
router.register(r'tour-instances', TourInstanceViewSet, basename='tour-instance')
router.register(r'tour-bookings', TourBookingViewSet, basename='tour-booking')
router.register(r'organizer-credits', OrganizerCreditViewSet, basename='organizer-credit')

urlpatterns = [
    path('', include(router.urls)),
]

