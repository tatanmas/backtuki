"""
🚀 ENTERPRISE PAYMENT URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaymentViewSet, PaymentMethodsPublicView, PaymentSetupView, TransbankUpdateView, PaymentProvidersListView

app_name = 'payment_processor'

router = DefaultRouter()
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('api/v1/', include(router.urls)),
    # Public endpoints
    path('api/v1/payment-methods/', PaymentMethodsPublicView.as_view(), name='payment-methods-public'),
    # Admin endpoints
    path('api/v1/admin/payment-providers/', PaymentProvidersListView.as_view(), name='payment-providers-list'),
    path('api/v1/admin/setup-payment-providers/', PaymentSetupView.as_view(), name='setup-payment-providers'),
    path('api/v1/admin/update-transbank-credentials/', TransbankUpdateView.as_view(), name='update-transbank-credentials'),
]
