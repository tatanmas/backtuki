"""URLs para API pública de alojamientos."""

from django.urls import path
from .views import (
    PublicAccommodationListView,
    PublicAccommodationDetailView,
    PublicAccommodationPricingPreviewView,
)

urlpatterns = [
    path("public/", PublicAccommodationListView.as_view(), name="public-accommodation-list"),
    path(
        "public/<str:slug_or_id>/",
        PublicAccommodationDetailView.as_view(),
        name="public-accommodation-detail",
    ),
    path(
        "public/<str:slug_or_id>/pricing-preview/",
        PublicAccommodationPricingPreviewView.as_view(),
        name="public-accommodation-pricing-preview",
    ),
]
