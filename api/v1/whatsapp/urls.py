"""WhatsApp API URLs."""
from django.urls import path
from . import views

# No usar app_name para evitar conflictos de namespace
# app_name = 'whatsapp'

urlpatterns = [
    path('webhook/process-message/', views.process_message, name='process-message'),
    path('webhook/operator-response/', views.process_operator_response, name='operator-response'),
    path('webhook/status/', views.webhook_status, name='webhook-status'),
    path('webhook/qr/', views.webhook_qr, name='webhook-qr'),
    path('generate-reservation-code/', views.generate_reservation_code, name='generate-reservation-code'),
]
