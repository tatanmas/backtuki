from django.urls import path
from .views import UserReservationsView, ReservationDetailView, get_reservations_by_email_otp

app_name = 'users'

urlpatterns = [
    # User reservations
    path('reservations/', UserReservationsView.as_view(), name='user_reservations'),
    path('reservations/<str:reservation_id>/', ReservationDetailView.as_view(), name='reservation_detail'),
    path('reservations/by-email/', get_reservations_by_email_otp, name='reservations_by_email'),
]
