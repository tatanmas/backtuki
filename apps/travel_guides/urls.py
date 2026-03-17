"""Public API URL configuration for travel guides."""

from django.urls import path
from .views import (
    PublicTravelGuideListView,
    PublicTravelGuideBySlugView,
    PublicTravelGuideExperienceBookingView,
)

urlpatterns = [
    path('', PublicTravelGuideListView.as_view(), name='public-travel-guide-list'),
    path('<str:slug>/experience-booking/<str:block_key>/', PublicTravelGuideExperienceBookingView.as_view(), name='public-travel-guide-experience-booking'),
    path('<str:slug>/', PublicTravelGuideBySlugView.as_view(), name='public-travel-guide-by-slug'),
]
