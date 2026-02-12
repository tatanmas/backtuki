"""URL Configuration for public schema API."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.landing_destinations.views import (
    PublicDestinationBySlugView,
    PublicDestinationWeatherTimeView,
)

# Import public viewsets
from api.v1.auth.views import (
    RegistrationView,
    LogoutView,
    PasswordResetView,
    PasswordResetConfirmView,
    UserProfileView,
)
from api.v1.organizers.views import CheckSubdomainAvailabilityView, CheckEmailAvailabilityView

# 🔐 OTP Authentication System - Import public OTP views
from apps.otp.views import (
    OTPGenerateView, 
    OTPValidateView, 
    OTPResendView, 
    OTPStatusView,
    EventCreationOTPView, 
    LoginOTPView, 
    TicketAccessOTPView
)

# Create a router and register our public viewsets
public_router = DefaultRouter()

# Wire up our API using automatic URL routing
urlpatterns = [
    path('', include(public_router.urls)),
    
    # Authentication URLs
    path('auth/register/', RegistrationView.as_view(), name='register'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/password-reset/', PasswordResetView.as_view(), name='password_reset'),
    path('auth/password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('auth/profile/', UserProfileView.as_view(), name='user_profile'),
    path('auth/', include('rest_framework.urls')),
    
    # Public organizer endpoints  
    path('organizers/check-subdomain/', CheckSubdomainAvailabilityView.as_view(), name='public_check_subdomain'),
    path('organizers/check-email/', CheckEmailAvailabilityView.as_view(), name='public_check_email'),
    
    # 🔐 OTP Authentication System - Public endpoints
    path('otp/generate/', OTPGenerateView.as_view(), name='otp_generate'),
    path('otp/validate/', OTPValidateView.as_view(), name='otp_validate'),
    path('otp/resend/', OTPResendView.as_view(), name='otp_resend'),
    path('otp/status/', OTPStatusView.as_view(), name='otp_status'),
    path('otp/event-creation/', EventCreationOTPView.as_view(), name='otp_event_creation'),
    path('otp/login/', LoginOTPView.as_view(), name='otp_login'),
    path('otp/ticket-access/', TicketAccessOTPView.as_view(), name='otp_ticket_access'),
    # Public landing destinations (página /destino/:slug)
    path('public/destinations/<str:slug>/', PublicDestinationBySlugView.as_view(), name='public-destination-by-slug'),
    path('public/destinations/<str:slug>/weather-time/', PublicDestinationWeatherTimeView.as_view(), name='public-destination-weather-time'),
] 