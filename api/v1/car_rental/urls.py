"""URLs for car rental public API."""

from django.urls import path
from .views import PublicCarListView, PublicCarDetailView, GenerateWhatsAppCodeView

urlpatterns = [
    path("public/", PublicCarListView.as_view(), name="public-car-list"),
    path(
        "public/<str:slug_or_id>/",
        PublicCarDetailView.as_view(),
        name="public-car-detail",
    ),
    path(
        "public/<str:slug_or_id>/generate-whatsapp-code/",
        GenerateWhatsAppCodeView.as_view(),
        name="public-car-generate-whatsapp-code",
    ),
]
