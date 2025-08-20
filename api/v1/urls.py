"""URL Configuration for API v1."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

# Import viewsets
from api.v1.users.views import UserViewSet
from api.v1.organizers.views import OrganizerViewSet, CurrentOnboardingView, OnboardingStepView, OnboardingCompleteView
from api.v1.events.views import (
    EventViewSet,
    EventCategoryViewSet,
    LocationViewSet,
    TicketTierViewSet,
    TicketCategoryViewSet,
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
    set_password_view,
)

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'organizers', OrganizerViewSet, basename='organizer')
router.register(r'events', EventViewSet, basename='event')
router.register(r'event-categories', EventCategoryViewSet, basename='event-category')
router.register(r'locations', LocationViewSet, basename='location')
router.register(r'ticket-tiers', TicketTierViewSet, basename='ticket-tier')
router.register(r'ticket-categories', TicketCategoryViewSet, basename='ticket-category')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'tickets', TicketViewSet, basename='ticket')
router.register(r'coupons', CouponViewSet, basename='coupon')
router.register(r'event-communications', EventCommunicationViewSet, basename='event-communication')
router.register(r'forms', FormViewSet, basename='form')

# Wire up our API using automatic URL routing
urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('api.v1.auth.urls')),
    # Onboarding URLs
    path('organizers/onboarding/start/', CurrentOnboardingView.as_view(), name='onboarding-start'),
    path('organizers/onboarding/step/', OnboardingStepView.as_view(), name='onboarding-step'),
    path('organizers/onboarding/complete/', OnboardingCompleteView.as_view(), name='onboarding-complete'),
] 