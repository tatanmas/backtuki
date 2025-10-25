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
from api.v1.forms.views import FormViewSet, FormResponseViewSet

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
router.register(r'form-responses', FormResponseViewSet, basename='form-response')

# Wire up our API using automatic URL routing
urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('api.v1.auth.urls')),
    path('user/', include('api.v1.users.urls')),
    path('tickets/', include('api.v1.tickets.urls')),  # 🚀 ENTERPRISE: Ticket management endpoints
    path('validation/', include('api.v1.validation.urls')),  # 🚀 ENTERPRISE: Validation system endpoints
    path('sync-woocommerce/', include('apps.sync_woocommerce.urls')),  # 🚀 ENTERPRISE: WooCommerce Sync System
    path('superadmin/', include('api.v1.superadmin.urls')),  # 🚀 ENTERPRISE: Super Admin management
    path('', include('api.v1.events.urls')),  # ✅ NUEVO: Incluir URLs de eventos (incluye endpoints públicos)
    # Onboarding URLs
    path('organizers/onboarding/start/', CurrentOnboardingView.as_view(), name='onboarding-start'),
    path('organizers/onboarding/step/', OnboardingStepView.as_view(), name='onboarding-step'),
    path('organizers/onboarding/complete/', OnboardingCompleteView.as_view(), name='onboarding-complete'),
] 