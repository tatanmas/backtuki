"""URLs for experiences API."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExperienceViewSet,
    TourLanguageViewSet,
    TourInstanceViewSet,
    TourBookingViewSet,
    OrganizerCreditViewSet,
    ExperienceResourceViewSet,
    ExperienceDatePriceOverrideViewSet,
    ExperienceReservationViewSet,
    PublicExperienceListView,
    PublicExperienceDetailView,
    PublicExperienceResourcesView,
    PublicExperienceInstancesView,
    PublicExperienceReviewsView,
    send_experience_email_sync,
)
from .booking_views import (
    PublicExperienceReserveView,
    PublicExperienceBookView,
)
from .public_reservation_view import get_reservation_by_organizer_token

router = DefaultRouter()
router.register(r'experiences', ExperienceViewSet, basename='experience')
router.register(r'tour-languages', TourLanguageViewSet, basename='tour-language')
router.register(r'tour-instances', TourInstanceViewSet, basename='tour-instance')
router.register(r'tour-bookings', TourBookingViewSet, basename='tour-booking')
router.register(r'organizer-credits', OrganizerCreditViewSet, basename='organizer-credit')
router.register(r'resources', ExperienceResourceViewSet, basename='experience-resource')
router.register(r'date-price-overrides', ExperienceDatePriceOverrideViewSet, basename='date-price-override')
router.register(r'reservations', ExperienceReservationViewSet, basename='experience-reservation')

urlpatterns = [
    # 🚀 ENTERPRISE: Organizer reservation by token (BEFORE router so path matches)
    path('reservations/public/<uuid:id>/', get_reservation_by_organizer_token, name='reservation-public-by-token'),
    path('', include(router.urls)),
    
    # Public endpoints
    path('public/', PublicExperienceListView.as_view(), name='public-experience-list'),
    path('public/<str:slug_or_id>/', PublicExperienceDetailView.as_view(), name='public-experience-detail'),
    path('public/<uuid:experience_id>/resources/', PublicExperienceResourcesView.as_view(), name='public-experience-resources'),
    path('public/<uuid:experience_id>/instances/', PublicExperienceInstancesView.as_view(), name='public-experience-instances'),
    path('public/<uuid:experience_id>/reviews/', PublicExperienceReviewsView.as_view(), name='public-experience-reviews'),
    path('public/<uuid:experience_id>/reserve/', PublicExperienceReserveView.as_view(), name='public-experience-reserve'),
    path('public/<uuid:experience_id>/book/', PublicExperienceBookView.as_view(), name='public-experience-book'),
    
    # 🚀 ENTERPRISE: Synchronous email endpoint
    path('orders/<str:order_number>/send-email/', send_experience_email_sync, name='send-experience-email-sync'),
]
