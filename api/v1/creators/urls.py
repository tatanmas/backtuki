"""URLs for TUKI Creators API."""

from django.urls import path
from .views import (
    PublicCreatorProfileView,
    CreatorMeView,
    CreatorRecommendedExperiencesView,
    LandingSlotsPublicView,
    RelatosMeView,
    RelatoMeDetailView,
    PublicRelatoView,
    CreatorMarketplaceView,
    CreatorPerformanceView,
    CreatorEarningsView,
)

urlpatterns = [
    path('landing-slots/', LandingSlotsPublicView.as_view(), name='creators-landing-slots'),
    path('public/<str:slug>/', PublicCreatorProfileView.as_view(), name='creators-public-profile'),
    path('public/<str:creator_slug>/relatos/<str:relato_slug>/', PublicRelatoView.as_view(), name='creators-public-relato'),
    path('me/', CreatorMeView.as_view(), name='creators-me'),
    path('me/recommended-experiences/', CreatorRecommendedExperiencesView.as_view(), name='creators-me-recommended'),
    path('me/recommended-experiences/<uuid:experience_id>/', CreatorRecommendedExperiencesView.as_view(), name='creators-me-recommended-delete'),
    path('me/relatos/', RelatosMeView.as_view(), name='creators-me-relatos'),
    path('me/relatos/<uuid:id>/', RelatoMeDetailView.as_view(), name='creators-me-relato-detail'),
    path('me/marketplace/', CreatorMarketplaceView.as_view(), name='creators-me-marketplace'),
    path('me/performance/', CreatorPerformanceView.as_view(), name='creators-me-performance'),
    path('me/earnings/', CreatorEarningsView.as_view(), name='creators-me-earnings'),
]
