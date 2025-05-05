"""URL Configuration for API v1."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Import viewsets
from api.v1.users.views import UserViewSet
from api.v1.organizers.views import OrganizerViewSet, OrganizerOnboardingViewSet
from api.v1.events.views import (
    EventViewSet,
    EventCategoryViewSet,
    LocationViewSet,
    TicketTierViewSet,
    TicketCategoryViewSet,
    EventFormViewSet,
    OrderViewSet,
    TicketViewSet,
    CouponViewSet,
    EventCommunicationViewSet,
)
from api.v1.forms.views import FormViewSet

from .auth.views import (
    EmailTokenObtainPairView,
    RegistrationView,
    PasswordResetView,
    PasswordResetConfirmView,
    UserProfileView,
    PasswordChangeView,
)

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'organizers', OrganizerViewSet, basename='organizer')
router.register(r'organizer-onboarding', OrganizerOnboardingViewSet, basename='organizer-onboarding')
router.register(r'events', EventViewSet, basename='event')
router.register(r'event-categories', EventCategoryViewSet, basename='event-category')
router.register(r'locations', LocationViewSet, basename='location')
router.register(r'ticket-tiers', TicketTierViewSet, basename='ticket-tier')
router.register(r'ticket-categories', TicketCategoryViewSet, basename='ticket-category')
router.register(r'event-forms', EventFormViewSet, basename='event-form')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'tickets', TicketViewSet, basename='ticket')
router.register(r'coupons', CouponViewSet, basename='coupon')
router.register(r'event-communications', EventCommunicationViewSet, basename='event-communication')
router.register(r'forms', FormViewSet, basename='form')

# Wire up our API using automatic URL routing
urlpatterns = [
    path('', include(router.urls)),
    
    # Auth endpoints
    path('auth/login/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/register/', RegistrationView.as_view(), name='user_register'),
    path('auth/password-reset/', PasswordResetView.as_view(), name='password_reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('auth/profile/', UserProfileView.as_view(), name='user_profile'),
    path('auth/change-password/', PasswordChangeView.as_view(), name='change_password'),
] 