from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TicketCategoryViewSet,
    TicketTierViewSet,
    generate_ticket_qr,
    validate_ticket_qr,
    send_order_email_sync,
    proxy_event_image,  # 🎫 ENTERPRISE: Image proxy for CORS
)
from .public_views import PublicEventViewSet

# ✅ Router para endpoints públicos ONLY
# EventViewSet is already registered in api/v1/urls.py to avoid duplicate registration
public_router = DefaultRouter()
public_router.register(r'public/events', PublicEventViewSet, basename='public-events')

# Nested routers for ticket categories and tiers
event_router = DefaultRouter()
event_router.register(r'ticket-categories', TicketCategoryViewSet, basename='event-ticket-category')
event_router.register(r'ticket-tiers', TicketTierViewSet, basename='event-ticket-tier')

urlpatterns = [
    path('', include(public_router.urls)),  # ✅ Public event endpoints
    path('events/<str:event_id>/', include(event_router.urls)),
    
    # Standalone ticket category endpoints
    path('ticket-categories/', TicketCategoryViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('ticket-categories/<str:pk>/', TicketCategoryViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'})),
    
    # Standalone ticket tier endpoints
    path('ticket-tiers/', TicketTierViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('ticket-tiers/<str:pk>/', TicketTierViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'})),
    
    # 🎫 ENTERPRISE QR CODE ENDPOINTS
    path('tickets/<str:ticket_number>/qr/', generate_ticket_qr, name='generate-ticket-qr'),
    path('tickets/validate-qr/', validate_ticket_qr, name='validate-ticket-qr'),
    
    # 📧 ENTERPRISE EMAIL ENDPOINTS
    path('orders/<str:order_number>/send-email/', send_order_email_sync, name='send-order-email-sync'),
    
    # 🎫 ENTERPRISE IMAGE PROXY (CORS fix for PDF generation)
    path('events/images/proxy/', proxy_event_image, name='proxy-event-image'),
] 