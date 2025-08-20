from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EventViewSet, 
    EventCategoryViewSet,
    TicketCategoryViewSet,
    TicketTierViewSet,
)

router = DefaultRouter()
router.register(r'events', EventViewSet)
router.register(r'event-categories', EventCategoryViewSet)

# Nested routers for ticket categories and tiers
event_router = DefaultRouter()
event_router.register(r'ticket-categories', TicketCategoryViewSet, basename='event-ticket-category')
event_router.register(r'ticket-tiers', TicketTierViewSet, basename='event-ticket-tier')

urlpatterns = [
    path('', include(router.urls)),
    path('events/<str:event_id>/', include(event_router.urls)),
    
    # Standalone ticket category endpoints
    path('ticket-categories/', TicketCategoryViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('ticket-categories/<str:pk>/', TicketCategoryViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'})),
    
    # Standalone ticket tier endpoints
    path('ticket-tiers/', TicketTierViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('ticket-tiers/<str:pk>/', TicketTierViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'})),
] 