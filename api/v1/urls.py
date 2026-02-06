"""URL Configuration for API v1."""

from django.urls import path, include
from django.conf import settings
from rest_framework.routers import DefaultRouter
from core.views import VersionView

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
    get_order_tickets,  # 🎫 ENTERPRISE: Get order tickets endpoint
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
    # Version (public, for checking what is deployed)
    path('version/', VersionView.as_view(), name='api-version'),
    # ⚠️ IMPORTANTE: Incluir organizers.urls ANTES del router para que tenga prioridad
    path('', include('api.v1.organizers.urls')),  # 🚀 Organizer profile management (incluyendo PATCH a /organizers/current/)
    
    # 🎫 ENTERPRISE: Order tickets endpoint (ANTES del router para que tenga prioridad sobre OrderViewSet)
    path('orders/<str:order_number>/tickets/', get_order_tickets, name='get-order-tickets'),
    
    # 🚀 ENTERPRISE: WhatsApp integration endpoints (ANTES del router para prioridad)
    path('whatsapp/', include('api.v1.whatsapp.urls')),
    
    path('', include(router.urls)),
    path('auth/', include('api.v1.auth.urls')),
    path('user/', include('api.v1.users.urls')),
    path('tickets/', include('api.v1.tickets.urls')),  # 🚀 ENTERPRISE: Ticket management endpoints
    path('media/', include('apps.media.urls')),  # 🚀 ENTERPRISE: Media Library System
    path('validation/', include('api.v1.validation.urls')),  # 🚀 ENTERPRISE: Validation system endpoints
    # WooCommerce Sync System (runtime toggle)
    *( [path('sync-woocommerce/', include('apps.sync_woocommerce.urls'))]
       if getattr(settings, 'WOOCOMMERCE_SYNC_ENABLED', False) else [] ),
    path('superadmin/', include('api.v1.superadmin.urls')),  # 🚀 ENTERPRISE: Super Admin management
    path('satisfaction/', include('apps.satisfaction.urls')),  # 🚀 ENTERPRISE: Satisfaction Survey System
    path('migration/', include('api.v1.migration.urls')),  # 🚀 ENTERPRISE: Backend-to-Backend Migration System
    path('', include('api.v1.events.urls')),  # ✅ NUEVO: Incluir URLs de eventos (incluye endpoints públicos)
    path('', include('api.v1.experiences.urls')),  # 🚀 ENTERPRISE: Experiences/Tours endpoints
    path('student-centers/', include('api.v1.student_centers.urls')),  # 🚀 ENTERPRISE: Student Centers endpoints
    path('creators/', include('api.v1.creators.urls')),  # 🚀 ENTERPRISE: TUKI Creators (influencers)
    path('terminal/', include('apps.terminal.urls')),  # 🚀 ENTERPRISE: Terminal bus schedule management
    # Onboarding URLs
    path('organizers/onboarding/start/', CurrentOnboardingView.as_view(), name='onboarding-start'),
    path('organizers/onboarding/step/', OnboardingStepView.as_view(), name='onboarding-step'),
    path('organizers/onboarding/complete/', OnboardingCompleteView.as_view(), name='onboarding-complete'),
] 