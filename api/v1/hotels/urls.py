"""URLs for public hotels API."""

from django.urls import path
from .views import PublicHotelDetailView, PublicHotelRoomsView

urlpatterns = [
    path("<str:slug>/", PublicHotelDetailView.as_view(), name="hotel-detail"),
    path("<str:slug>/rooms/", PublicHotelRoomsView.as_view(), name="hotel-rooms"),
]
