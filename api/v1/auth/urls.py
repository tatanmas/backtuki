"""URL Configuration for authentication API."""

from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from .views import (
    RegistrationView,
    LogoutView,
    PasswordResetView,
    PasswordResetConfirmView,
    UserProfileView,
    set_password_view,
)

urlpatterns = [
    path('token/', obtain_auth_token, name='token_obtain'),
    path('register/', RegistrationView.as_view(), name='register'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password-reset/', PasswordResetView.as_view(), name='password_reset'),
    path('password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('set-password/', set_password_view, name='set_password'),
] 