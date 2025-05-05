from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import OrganizerViewSet, OrganizerOnboardingViewSet

router = DefaultRouter()

# The organizer views are already registered in the main v1 urls file,
# so we don't need to register them again here. 
# This file simply provides a place to add any organizer-specific URL patterns.

urlpatterns = [
    # Add any organizer-specific URL patterns here if needed
] 