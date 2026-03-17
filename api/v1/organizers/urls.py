from django.urls import path
from .views import (
    OnboardingStepView,
    CurrentOnboardingView,
    CurrentOrganizerView,
    OrganizerLogoUploadView,
    DashboardStatsView,
    OrganizerFinancesView,
)
from .views_accommodations import (
    OrganizerAccommodationListView,
    OrganizerAccommodationDetailView,
    OrganizerAccommodationGalleryView,
    organizer_accommodation_blocked_dates,
)

urlpatterns = [
    # Onboarding endpoints
    path('organizer-onboarding/save_step/', OnboardingStepView.as_view(), name='save_onboarding_step'),
    path('organizer-onboarding/current/', CurrentOnboardingView.as_view(), name='current_onboarding'),

    # Organizer endpoints
    path('organizers/current/', CurrentOrganizerView.as_view(), name='current_organizer'),
    path('organizers/current/upload-logo/', OrganizerLogoUploadView.as_view(), name='upload_organizer_logo'),
    path('organizers/dashboard-stats/', DashboardStatsView.as_view(), name='organizer_dashboard_stats'),
    path('organizers/finances/', OrganizerFinancesView.as_view(), name='organizer_finances'),

    # Organizer accommodation endpoints
    path('organizers/accommodations/', OrganizerAccommodationListView.as_view(), name='organizer_accommodations_list'),
    path('organizers/accommodations/<uuid:accommodation_id>/', OrganizerAccommodationDetailView.as_view(), name='organizer_accommodations_detail'),
    path('organizers/accommodations/<uuid:accommodation_id>/gallery/', OrganizerAccommodationGalleryView.as_view(), name='organizer_accommodations_gallery'),
    path('organizers/accommodations/<uuid:accommodation_id>/blocked-dates/', organizer_accommodation_blocked_dates, name='organizer_accommodations_blocked_dates'),
] 