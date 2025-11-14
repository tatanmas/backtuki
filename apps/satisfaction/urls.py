"""
URLs for Satisfaction Survey System
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SatisfactionSurveyViewSet, public_survey_view

router = DefaultRouter()
router.register(r'surveys', SatisfactionSurveyViewSet, basename='satisfaction-survey')

urlpatterns = [
    path('', include(router.urls)),
    path('public/<slug:slug>/', public_survey_view, name='public-survey'),
]

