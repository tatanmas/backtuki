from django.urls import path
from .views import (
    OnboardingStepView,
    CurrentOnboardingView,
    CurrentOrganizerView,
    # Remove OrganizerViewSet and other unused views if any
)

urlpatterns = [
    # Onboarding endpoints
    path('organizer-onboarding/save_step/', OnboardingStepView.as_view(), name='save_onboarding_step'),
    path('organizer-onboarding/current/', CurrentOnboardingView.as_view(), name='current_onboarding'),
    
    # Organizer endpoints
    path('organizers/current/', CurrentOrganizerView.as_view(), name='current_organizer'),
] 