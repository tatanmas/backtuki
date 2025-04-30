"""URL Configuration for public schema API."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Import public viewsets
from api.v1.auth.views import (
    RegistrationView,
    LogoutView,
    PasswordResetView,
    PasswordResetConfirmView,
    UserProfileView,
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
] 