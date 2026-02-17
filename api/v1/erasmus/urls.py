from django.urls import path
from .views import (
    ErasmusOptionsView,
    ErasmusRegisterView,
    ErasmusMyGuidesView,
    ErasmusTrackVisitView,
    ErasmusTrackStepView,
)

urlpatterns = [
    path("options/", ErasmusOptionsView.as_view(), name="erasmus-options"),
    path("track-visit/", ErasmusTrackVisitView.as_view(), name="erasmus-track-visit"),
    path("track-step/", ErasmusTrackStepView.as_view(), name="erasmus-track-step"),
    path("register/", ErasmusRegisterView.as_view(), name="erasmus-register"),
    path("my-guides/", ErasmusMyGuidesView.as_view(), name="erasmus-my-guides"),
]
