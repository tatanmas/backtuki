"""
🚀 ENTERPRISE PAYMENT URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaymentViewSet, PaymentMethodsPublicView, PaymentSetupView

app_name = 'payment_processor'

router = DefaultRouter()
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('api/v1/', include(router.urls)),
    # Public endpoints
    path('api/v1/payment-methods/', PaymentMethodsPublicView.as_view(), name='payment-methods-public'),
    # Admin endpoints
    path('api/v1/admin/setup-payment-providers/', PaymentSetupView.as_view(), name='setup-payment-providers'),
]
