"""
🚀 ENTERPRISE PAYMENT PROCESSOR MODELS
Multi-provider payment system designed for high concurrency and scalability.
"""

from django.db import models
from django.utils import timezone
from core.models import BaseModel
import uuid
import json


class PaymentProvider(BaseModel):
    """
    🚀 ENTERPRISE: Payment providers (Transbank, MercadoPago, Stripe, etc.)
    """
    PROVIDER_CHOICES = [
        ('transbank_webpay_plus', 'Transbank WebPay Plus'),
        ('transbank_oneclick', 'Transbank Oneclick'),
        ('mercadopago', 'MercadoPago'),
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    provider_type = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    is_active = models.BooleanField(default=True)
    is_sandbox = models.BooleanField(default=True)
    
    # Configuration (encrypted in production)
    config = models.JSONField(default=dict, help_text="Provider-specific configuration")
    
    # Limits and settings
    min_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    supported_currencies = models.JSONField(default=list, help_text="['CLP', 'USD']")
    
    # Enterprise features
    priority = models.IntegerField(default=0, help_text="Higher priority = preferred provider")
    timeout_seconds = models.IntegerField(default=30)
    retry_attempts = models.IntegerField(default=3)
    
    class Meta:
        ordering = ['-priority', 'name']
    
    def __str__(self):
        env = "SANDBOX" if self.is_sandbox else "PRODUCTION"
        return f"{self.name} ({env})"


class PaymentMethod(BaseModel):
    """
    🚀 ENTERPRISE: Payment methods available to customers
    """
    METHOD_TYPES = [
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('wallet', 'Digital Wallet'),
        ('saved_card', 'Saved Card (Oneclick)'),
    ]
    
    provider = models.ForeignKey(PaymentProvider, on_delete=models.CASCADE, related_name='payment_methods')
    method_type = models.CharField(max_length=50, choices=METHOD_TYPES)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    is_active = models.BooleanField(default=True)
    requires_registration = models.BooleanField(default=False)  # For Oneclick
    
    # UI/UX
    icon_url = models.URLField(blank=True)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order', 'display_name']
        unique_together = ['provider', 'method_type']
    
    def __str__(self):
        return f"{self.display_name} ({self.provider.name})"


class Payment(BaseModel):
    """
    🚀 ENTERPRISE: Main payment entity - handles all payment transactions
    """
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('authorized', 'Authorized'),
        ('captured', 'Captured'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('partially_refunded', 'Partially Refunded'),
    ]
    
    # Core payment data
    order = models.ForeignKey('events.Order', on_delete=models.CASCADE, related_name='payments')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    
    # Financial data
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='CLP')
    
    # Status and tracking
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    external_id = models.CharField(max_length=255, blank=True, help_text="Provider's transaction ID")
    
    # Transbank specific
    token = models.CharField(max_length=255, blank=True, help_text="Transbank token")
    buy_order = models.CharField(max_length=26, unique=True, help_text="Unique buy order")
    
    # Timestamps
    authorized_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, help_text="Additional provider-specific data")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['buy_order']),
            models.Index(fields=['external_id']),
            models.Index(fields=['token']),
        ]
    
    def __str__(self):
        return f"Payment {self.buy_order} - {self.status} - ${self.amount}"
    
    def generate_buy_order(self):
        """Generate unique buy order for Transbank"""
        if not self.buy_order:
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            self.buy_order = f"TK{timestamp}{str(uuid.uuid4())[:8]}"
        return self.buy_order
    
    def is_pending(self):
        return self.status in ['pending', 'processing', 'authorized']
    
    def is_successful(self):
        return self.status in ['captured', 'completed']
    
    def is_failed(self):
        return self.status in ['failed', 'cancelled']


class PaymentTransaction(BaseModel):
    """
    🚀 ENTERPRISE: Individual transaction log for audit and debugging
    """
    TRANSACTION_TYPES = [
        ('create', 'Create Payment'),
        ('authorize', 'Authorize'),
        ('capture', 'Capture'),
        ('refund', 'Refund'),
        ('cancel', 'Cancel'),
        ('webhook', 'Webhook Received'),
        ('status_check', 'Status Check'),
    ]
    
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    
    # Request/Response data for debugging
    request_data = models.JSONField(default=dict)
    response_data = models.JSONField(default=dict)
    
    # Status
    is_successful = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    
    # Timing
    duration_ms = models.IntegerField(null=True, help_text="Request duration in milliseconds")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment', 'created_at']),
            models.Index(fields=['transaction_type', 'created_at']),
        ]
    
    def __str__(self):
        status = "✅" if self.is_successful else "❌"
        return f"{status} {self.transaction_type} - {self.payment.buy_order}"


class SavedCard(BaseModel):
    """
    🚀 ENTERPRISE: Saved cards for Oneclick (Transbank)
    """
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='saved_cards')
    
    # Transbank Oneclick data
    username = models.CharField(max_length=100, help_text="Oneclick username")
    tbk_user = models.CharField(max_length=100, help_text="Transbank user token")
    
    # Card info (masked)
    card_type = models.CharField(max_length=50, blank=True)  # Visa, Mastercard, etc.
    last_four_digits = models.CharField(max_length=4, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    
    # Metadata
    card_metadata = models.JSONField(default=dict)
    
    class Meta:
        unique_together = ['user', 'tbk_user']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Card ***{self.last_four_digits} - {self.user.email}"


class PaymentWebhook(BaseModel):
    """
    🚀 ENTERPRISE: Webhook events from payment providers
    """
    WEBHOOK_STATUS = [
        ('received', 'Received'),
        ('processing', 'Processing'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
        ('ignored', 'Ignored'),
    ]
    
    provider = models.ForeignKey(PaymentProvider, on_delete=models.CASCADE)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, null=True, blank=True)
    
    # Webhook data
    event_type = models.CharField(max_length=100)
    webhook_id = models.CharField(max_length=255, unique=True)
    
    # Raw data
    headers = models.JSONField(default=dict)
    payload = models.JSONField(default=dict)
    
    # Processing
    status = models.CharField(max_length=20, choices=WEBHOOK_STATUS, default='received')
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['webhook_id']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"Webhook {self.event_type} - {self.status}"