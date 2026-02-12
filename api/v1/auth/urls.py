"""URL Configuration for authentication API."""

from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
    TokenVerifyView,
)
from .views import (
    RegistrationView,
    LogoutView,
    PasswordResetView,
    PasswordResetConfirmView,
    UserProfileView,
    set_password_view,
    EmailTokenObtainPairView,
    PasswordChangeView,
    CheckUserView,
    LoginView,
    OTPLoginView,
    MagicLoginView,
    OrganizerMagicLoginView,
    create_guest_user_from_purchase,
    OrganizerOTPSendView,
    OrganizerOTPValidateView,
    OrganizerProfileSetupView,
)

urlpatterns = [
    # JWT endpoints
    path('token/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # OTP Authentication System
    path('check-user/', CheckUserView.as_view(), name='check_user'),
    path('login-password/', LoginView.as_view(), name='login_password'),
    path('login/otp/', OTPLoginView.as_view(), name='otp_login'),
    path('magic-login/', MagicLoginView.as_view(), name='magic_login'),
    path('organizer-magic-login/', OrganizerMagicLoginView.as_view(), name='organizer_magic_login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    
    # User Profile
    path('me/', UserProfileView.as_view(), name='user_profile'),
    path('profile/', UserProfileView.as_view(), name='update_profile'),
    
    # Guest User Creation (for purchases)
    path('create-guest/', create_guest_user_from_purchase, name='create_guest'),
    
    # Traditional Registration (with OTP)
    path('register/', RegistrationView.as_view(), name='register'),
    
    # Organizer OTP Authentication
    path('organizer/otp/send/', OrganizerOTPSendView.as_view(), name='organizer_otp_send'),
    path('organizer/otp/validate/', OrganizerOTPValidateView.as_view(), name='organizer_otp_validate'),
    path('organizer/profile/setup/', OrganizerProfileSetupView.as_view(), name='organizer_profile_setup'),
    
    # Password Management
    path('change-password/', PasswordChangeView.as_view(), name='change_password'),
    path('password-reset/', PasswordResetView.as_view(), name='password_reset'),
    path('password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('set-password/', set_password_view, name='set_password'),  # Legacy
] 