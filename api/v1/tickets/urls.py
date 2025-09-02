"""
🚀 ENTERPRISE: Ticket management URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TicketTierManagementViewSet

router = DefaultRouter()
router.register(r'ticket-tiers', TicketTierManagementViewSet, basename='ticket-tier-management')

urlpatterns = [
    path('', include(router.urls)),
]
