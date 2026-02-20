"""URLs for rental hubs API."""

from django.urls import path
from .views import PublicRentalHubDetailView, PublicRentalHubAccommodationsView

urlpatterns = [
    path("<str:slug>/", PublicRentalHubDetailView.as_view(), name="rental-hub-detail"),
    path(
        "<str:slug>/accommodations/",
        PublicRentalHubAccommodationsView.as_view(),
        name="rental-hub-accommodations",
    ),
]
