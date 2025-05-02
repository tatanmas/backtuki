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
)

urlpatterns = [
    # JWT endpoints
    path('token/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # Registration and user management
    path('register/', RegistrationView.as_view(), name='register'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password-reset/', PasswordResetView.as_view(), name='password_reset'),
    path('password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('set-password/', set_password_view, name='set_password'),
    path('change-password/', PasswordChangeView.as_view(), name='change_password'),
] 