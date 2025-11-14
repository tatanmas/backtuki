"""
URLs para la API de sincronización WooCommerce
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SyncConfigurationViewSet,
    SyncExecutionViewSet,
    SyncCredentialsViewSet,
    SyncManagementViewSet
)

# Router para ViewSets
router = DefaultRouter()
router.register(r'configurations', SyncConfigurationViewSet, basename='sync-configurations')
router.register(r'executions', SyncExecutionViewSet, basename='sync-executions')
router.register(r'credentials', SyncCredentialsViewSet, basename='sync-credentials')
router.register(r'management', SyncManagementViewSet, basename='sync-management')

app_name = 'sync_woocommerce'

urlpatterns = [
    path('', include(router.urls)),
]
