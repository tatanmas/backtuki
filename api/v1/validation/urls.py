"""
🚀 ENTERPRISE VALIDATION URLs
URLs para el sistema de validación enterprise
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router para ViewSets
router = DefaultRouter()

# URLs de validación enterprise
urlpatterns = [
    # 🚀 ENTERPRISE VALIDATION ENDPOINTS
    path('validator/session/start/', views.start_validator_session, name='start-validator-session'),
    path('validator/ticket/validate/', views.validate_ticket_enterprise, name='validate-ticket-enterprise'),
    path('validator/ticket/<int:ticket_id>/checkin/', views.checkin_ticket_enterprise, name='checkin-ticket-enterprise'),
    
    # Endpoints adicionales para el sistema completo
    path('validator/session/<int:session_id>/end/', views.end_validator_session, name='end-validator-session'),
    path('validator/session/<int:session_id>/stats/', views.get_session_stats, name='get-session-stats'),
    path('validator/ticket/<int:ticket_id>/notes/', views.add_ticket_note, name='add-ticket-note'),
    path('validator/event/<int:event_id>/tickets/', views.get_event_tickets, name='get-event-tickets'),
    path('validator/event/<int:event_id>/stats/', views.get_event_validation_stats, name='get-event-validation-stats'),
    
    # Include router URLs
    path('', include(router.urls)),
]

