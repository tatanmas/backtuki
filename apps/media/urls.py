"""
🚀 ENTERPRISE MEDIA LIBRARY URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.media import views

router = DefaultRouter()
router.register(r'assets', views.MediaAssetViewSet, basename='media-asset')

urlpatterns = [
    path('', include(router.urls)),
]

