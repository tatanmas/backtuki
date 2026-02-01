from django.urls import path
from .views import (
    OnboardingStepView,
    CurrentOnboardingView,
    CurrentOrganizerView,
    OrganizerLogoUploadView,
    DashboardStatsView,
)

urlpatterns = [
    # Onboarding endpoints
    path('organizer-onboarding/save_step/', OnboardingStepView.as_view(), name='save_onboarding_step'),
    path('organizer-onboarding/current/', CurrentOnboardingView.as_view(), name='current_onboarding'),
    
    # Organizer endpoints
    path('organizers/current/', CurrentOrganizerView.as_view(), name='current_organizer'),
    path('organizers/current/upload-logo/', OrganizerLogoUploadView.as_view(), name='upload_organizer_logo'),
    path('organizers/dashboard-stats/', DashboardStatsView.as_view(), name='organizer_dashboard_stats'),
] 