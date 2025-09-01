from django.urls import path
from .views import (
    OTPGenerateView, OTPValidateView, OTPResendView, OTPStatusView,
    EventCreationOTPView, LoginOTPView, TicketAccessOTPView,
    cleanup_expired_codes
)

app_name = 'otp'

urlpatterns = [
    # Endpoints generales de OTP
    path('generate/', OTPGenerateView.as_view(), name='generate'),
    path('validate/', OTPValidateView.as_view(), name='validate'),
    path('resend/', OTPResendView.as_view(), name='resend'),
    path('status/', OTPStatusView.as_view(), name='status'),
    
    # Endpoints específicos por propósito
    path('event-creation/', EventCreationOTPView.as_view(), name='event_creation'),
    path('login/', LoginOTPView.as_view(), name='login'),
    path('ticket-access/', TicketAccessOTPView.as_view(), name='ticket_access'),
    
    # Endpoint administrativo
    path('cleanup/', cleanup_expired_codes, name='cleanup'),
]
