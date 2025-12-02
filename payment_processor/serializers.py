"""
🚀 ENTERPRISE PAYMENT SERIALIZERS
High-performance serializers for payment processing API.
"""

from rest_framework import serializers
from decimal import Decimal
from .models import Payment, PaymentProvider, PaymentMethod, PaymentTransaction, SavedCard
from apps.events.models import Order


class PaymentProviderSerializer(serializers.ModelSerializer):
    """Serializer for payment providers (public info only)"""
    
    class Meta:
        model = PaymentProvider
        fields = [
            'id', 'name', 'provider_type', 'is_active', 
            'min_amount', 'max_amount', 'supported_currencies'
        ]


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for payment methods"""
    
    provider = PaymentProviderSerializer(read_only=True)
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'provider', 'method_type', 'display_name', 
            'description', 'icon_url', 'requires_registration'
        ]


class CreatePaymentSerializer(serializers.Serializer):
    """
    🚀 ENTERPRISE: Serializer for creating payments
    """
    order_id = serializers.UUIDField()
    payment_method_id = serializers.UUIDField(required=False)
    provider_type = serializers.CharField(required=False)
    method_type = serializers.CharField(required=False)
    return_url = serializers.URLField(required=False)
    
    def validate_order_id(self, value):
        """Validate that order exists and is pending"""
        try:
            order = Order.objects.get(id=value)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found")
        
        if order.status != 'pending':
            raise serializers.ValidationError("Order is not in pending status")
        
        # Check if order already has a successful payment
        if order.payments.filter(status__in=['completed', 'captured']).exists():
            raise serializers.ValidationError("Order already has a successful payment")
        
        return value
    
    def validate_payment_method_id(self, value):
        """Validate payment method exists and is active"""
        if value:  # Only validate if provided
            try:
                method = PaymentMethod.objects.get(id=value, is_active=True)
            except PaymentMethod.DoesNotExist:
                raise serializers.ValidationError("Payment method not found or inactive")
        
        return value
    
    def validate(self, attrs):
        """Cross-field validation"""
        order = Order.objects.get(id=attrs['order_id'])
        
        # 🚀 ENTERPRISE: Support both ID and type-based lookup
        payment_method_id = attrs.get('payment_method_id')
        provider_type = attrs.get('provider_type')
        method_type = attrs.get('method_type')
        
        if payment_method_id:
            # Traditional ID lookup
            method = PaymentMethod.objects.get(id=payment_method_id)
        elif provider_type and method_type:
            # 🚀 NEW: Type-based lookup (ROBUST)
            try:
                method = PaymentMethod.objects.get(
                    provider__provider_type=provider_type,
                    method_type=method_type,
                    is_active=True,
                    provider__is_active=True
                )
                # Store the resolved ID for later use
                attrs['payment_method_id'] = method.id
            except PaymentMethod.DoesNotExist:
                raise serializers.ValidationError(
                    f"Payment method not found for provider_type='{provider_type}' and method_type='{method_type}'"
                )
        else:
            raise serializers.ValidationError(
                "Either payment_method_id or both provider_type and method_type must be provided"
            )
        
        # Validate amount limits
        if order.total < method.provider.min_amount:
            raise serializers.ValidationError(
                f"Amount ${order.total} is below minimum ${method.provider.min_amount}"
            )
        
        if method.provider.max_amount and order.total > method.provider.max_amount:
            raise serializers.ValidationError(
                f"Amount ${order.total} exceeds maximum ${method.provider.max_amount}"
            )
        
        # Validate currency
        if 'CLP' not in method.provider.supported_currencies:
            raise serializers.ValidationError("Currency CLP not supported by this provider")
        
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    """
    🚀 ENTERPRISE: Serializer for payment responses
    """
    payment_method = PaymentMethodSerializer(read_only=True)
    order_id = serializers.UUIDField(source='order.id', read_only=True)
    order_total = serializers.DecimalField(source='order.total', max_digits=10, decimal_places=2, read_only=True)
    
    # Event information for frontend
    event_info = serializers.SerializerMethodField()
    
    # Frontend-friendly field names
    paymentId = serializers.UUIDField(source='id', read_only=True)
    paymentStatus = serializers.CharField(source='status', read_only=True)
    paymentAmount = serializers.DecimalField(source='amount', max_digits=10, decimal_places=2, read_only=True)
    buyOrder = serializers.CharField(source='buy_order', read_only=True)
    externalId = serializers.CharField(source='external_id', read_only=True)
    
    # Timestamps
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    authorizedAt = serializers.DateTimeField(source='authorized_at', read_only=True)
    completedAt = serializers.DateTimeField(source='completed_at', read_only=True)
    
    def get_event_info(self, obj):
        """Get event information for the payment."""
        try:
            event = obj.order.event
            
            # Get event image
            event_image = None
            if event.images.exists():
                first_image = event.images.first()
                if first_image and first_image.image:
                    event_image = first_image.image.url
            
            # Get location info
            location_info = {
                'name': 'Ubicación no disponible',
                'address': ''
            }
            if event.location:
                location_info = {
                    'name': event.location.name,
                    'address': event.location.address
                }
            
            return {
                'id': str(event.id),
                'title': event.title,
                'date': event.start_date.isoformat() if event.start_date else None,
                'location': location_info,
                'image': event_image,
                'ticket_holders': self._get_ticket_holders(obj.order)
            }
        except Exception as e:
            print(f"Error getting event info for payment {obj.id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_ticket_holders(self, order):
        """
        Get ticket holders information including ticket numbers for PDF generation.
        
        Returns list of dicts with:
        - name: Full name of ticket holder
        - email: Email address
        - tier_name: Ticket tier name
        - ticket_number: Unique ticket identifier (for QR and PDF)
        - ticket_id: UUID of ticket (optional, for future use)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        holders = []
        try:
            logger.info(f"🎫 [PDF] Getting ticket holders for order {order.order_number}")
            items_count = order.items.count()
            logger.info(f"🎫 [PDF] Order has {items_count} items")
            
            for item in order.items.all():
                tickets_count = item.tickets.count()
                logger.info(f"🎫 [PDF] Item {item.id} has {tickets_count} tickets")
                
                for ticket in item.tickets.all():
                    holder_data = {
                        'name': f"{ticket.first_name} {ticket.last_name}".strip(),
                        'email': ticket.email,
                        'tier_name': item.ticket_tier.name if item.ticket_tier else 'General',
                        'ticket_number': ticket.ticket_number,  # 🎫 NEW: For PDF QR generation
                        'ticket_id': str(ticket.id),  # 🎫 NEW: For future features
                    }
                    holders.append(holder_data)
                    logger.info(f"🎫 [PDF] Added holder: {holder_data['name']} ({holder_data['ticket_number']})")
            
            logger.info(f"🎫 [PDF] Total holders returned: {len(holders)}")
        except Exception as e:
            logger.error(f"❌ [PDF] Error getting ticket holders: {e}", exc_info=True)
        return holders
    
    class Meta:
        model = Payment
        fields = [
            'id', 'paymentId', 'order_id', 'order_total', 'payment_method',
            'amount', 'paymentAmount', 'currency', 'status', 'paymentStatus',
            'buy_order', 'buyOrder', 'external_id', 'externalId', 'token',
            'created_at', 'createdAt', 'authorized_at', 'authorizedAt', 
            'completed_at', 'completedAt', 'metadata', 'event_info'
        ]


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Serializer for payment transactions (for debugging/admin)"""
    
    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'transaction_type', 'is_successful', 'error_message',
            'duration_ms', 'created_at'
        ]


class PaymentStatusSerializer(serializers.Serializer):
    """
    🚀 ENTERPRISE: Serializer for payment status responses
    """
    payment = PaymentSerializer()
    transaction_data = serializers.JSONField(required=False)
    redirect_url = serializers.URLField(required=False)
    
    # Status flags for frontend
    is_pending = serializers.BooleanField()
    is_successful = serializers.BooleanField()
    is_failed = serializers.BooleanField()
    requires_action = serializers.BooleanField(default=False)
    
    # User-friendly messages
    status_message = serializers.CharField()
    next_action = serializers.CharField(required=False)


class WebPayReturnSerializer(serializers.Serializer):
    """
    🚀 ENTERPRISE: Serializer for WebPay return data
    """
    token_ws = serializers.CharField(max_length=255)
    
    def validate_token_ws(self, value):
        """Validate that token exists in our system"""
        try:
            payment = Payment.objects.get(token=value)
        except Payment.DoesNotExist:
            raise serializers.ValidationError("Invalid token")
        
        return value


class SavedCardSerializer(serializers.ModelSerializer):
    """Serializer for saved cards (Oneclick)"""
    
    # Frontend-friendly names
    cardId = serializers.UUIDField(source='id', read_only=True)
    cardType = serializers.CharField(source='card_type', read_only=True)
    lastFourDigits = serializers.CharField(source='last_four_digits', read_only=True)
    isActive = serializers.BooleanField(source='is_active', read_only=True)
    isVerified = serializers.BooleanField(source='is_verified', read_only=True)
    
    class Meta:
        model = SavedCard
        fields = [
            'id', 'cardId', 'card_type', 'cardType', 
            'last_four_digits', 'lastFourDigits',
            'is_active', 'isActive', 'is_verified', 'isVerified',
            'created_at'
        ]


class PaymentSummarySerializer(serializers.Serializer):
    """
    🚀 ENTERPRISE: Payment summary for checkout
    """
    available_methods = PaymentMethodSerializer(many=True)
    order_summary = serializers.SerializerMethodField()
    payment_limits = serializers.SerializerMethodField()
    
    def get_order_summary(self, obj):
        """Get order summary"""
        order = obj.get('order')
        if not order:
            return None
        
        return {
            'order_id': str(order.id),
            'total': float(order.total),
            'subtotal': float(order.subtotal),
            'service_fee': float(order.service_fee),
            'currency': 'CLP',
            'items_count': order.items.count()
        }
    
    def get_payment_limits(self, obj):
        """Get payment limits for all providers"""
        methods = obj.get('available_methods', [])
        limits = {}
        
        for method in methods:
            provider = method.provider
            limits[str(method.id)] = {
                'min_amount': float(provider.min_amount),
                'max_amount': float(provider.max_amount) if provider.max_amount else None,
                'supported_currencies': provider.supported_currencies
            }
        
        return limits
