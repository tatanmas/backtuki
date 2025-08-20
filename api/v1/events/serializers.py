"""Serializers for events API."""

from rest_framework import serializers
from django.utils import timezone
from django.utils.text import slugify
from django.db import transaction
import uuid
from typing import List, Optional, Dict, Any, Union

from apps.events.models import (
    Event,
    EventCategory,
    Location,
    EventImage,
    TicketTier,
    TicketCategory,
    Order,
    OrderItem,
    Ticket,
    TicketNote,
    EmailLog,
    Coupon,
    EventCommunication,
    SimpleBooking,
    TicketRequest,
)
from apps.forms.models import Form, FormField
from apps.forms.serializers import FormFieldSerializer, FormSerializer
from apps.organizers.models import OrganizerUser

# Import payment processor models for payment details
try:
    from payment_processor.models import Payment
except ImportError:
    Payment = None


class LocationSerializer(serializers.ModelSerializer):
    """
    Serializer for location model - supports both physical and virtual locations.
    """
    is_virtual = serializers.ReadOnlyField()
    
    class Meta:
        model = Location
        fields = ['id', 'name', 'address', 'is_virtual']
        read_only_fields = ['id', 'is_virtual']


class EventCategorySerializer(serializers.ModelSerializer):
    """
    Serializer for event category model.
    """
    class Meta:
        model = EventCategory
        fields = ['id', 'name', 'slug', 'description', 'icon']
        read_only_fields = ['id', 'slug']


class EventImageSerializer(serializers.ModelSerializer):
    """
    Serializer for event image model.
    """
    class Meta:
        model = EventImage
        fields = ['id', 'image', 'alt', 'type', 'order']
        read_only_fields = ['id']


class TicketCategorySerializer(serializers.ModelSerializer):
    """
    Serializer for ticket category model.
    """
    available = serializers.IntegerField(read_only=True)
    is_sold_out = serializers.BooleanField(read_only=True)
    has_capacity_limit = serializers.SerializerMethodField()
    
    class Meta:
        model = TicketCategory
        fields = [
            'id', 'name', 'description', 'capacity', 'sold', 'available',
            'status', 'visibility', 'color', 'order', 'max_per_purchase',
            'min_per_purchase', 'sale_start_date', 'sale_end_date',
            'sale_start_time', 'sale_end_time', 'access_start_date',
            'access_end_date', 'access_start_time', 'access_end_time',
            'is_sold_out', 'has_capacity_limit', 'requires_approval'
        ]
        read_only_fields = ['id', 'sold', 'available', 'is_sold_out']

    def get_has_capacity_limit(self, obj):
        """Return True if the category has a capacity limit."""
        return obj.capacity is not None


class TicketTierSerializer(serializers.ModelSerializer):
    """
    Serializer for ticket tier model.
    """
    price = serializers.SerializerMethodField()
    benefits = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()
    
    class Meta:
        model = TicketTier
        fields = [
            'id', 'name', 'type', 'description', 'price',
            'capacity', 'available', 'is_public', 'max_per_order',
            'min_per_order', 'benefits', 'metadata', 'requires_approval'
        ]
        read_only_fields = ['id', 'available']

    def get_price(self, obj) -> Dict[str, Union[float, str, List[Dict[str, Union[str, float]]]]]:
        """Return price information."""
        price_data = {
            'basePrice': float(obj.price),
            'currency': obj.currency,
        }
        
        # Add service fee if present
        if obj.service_fee:
            price_data['serviceFee'] = float(obj.service_fee)
        
        # Add original price and discount info if it's a discounted ticket
        if obj.original_price:
            price_data['originalAmount'] = float(obj.original_price)
            
            # Calculate discount
            discount_amount = float(obj.original_price) - float(obj.price)
            if discount_amount > 0:
                price_data['discounts'] = [
                    {
                        'type': obj.type,
                        'amount': discount_amount,
                        'description': f'Descuento {obj.type}'
                    }
                ]
        
        return price_data
    
    def get_benefits(self, obj) -> List[str]:
        """Return benefits as a list."""
        return obj.benefits_list if obj.benefits else []
    
    def get_metadata(self, obj) -> Dict[str, Any]:
        """Return additional metadata."""
        category = obj.category
        metadata = {}
        
        if category:
            metadata['category'] = category.id  # Use category ID for frontend mapping
            metadata['categoryId'] = category.id  # Explicit categoryId field
            metadata['categoryName'] = category.name  # Keep name for display
            metadata['categoryDescription'] = category.description
        
        # Add form information if present
        if obj.form:
            metadata['formId'] = obj.form.id
            metadata['formName'] = obj.form.name
        
        if obj.is_highlighted:
            metadata['isHighlighted'] = True
        
        if obj.is_waitlist:
            metadata['isWaitlist'] = True
        
        if obj.image:
            metadata['image'] = self.context['request'].build_absolute_uri(obj.image.url)
        
        return metadata


class CouponSerializer(serializers.ModelSerializer):
    """
    Serializer for coupon model.
    """
    is_active = serializers.BooleanField(required=False, default=True)
    events = serializers.SerializerMethodField()
    maxUses = serializers.IntegerField(source='usage_limit', required=False, allow_null=True)
    usedCount = serializers.IntegerField(source='usage_count', read_only=True)
    
    # 🚀 ENTERPRISE: Fields to distinguish global vs local coupons
    is_global = serializers.SerializerMethodField()
    coupon_scope = serializers.SerializerMethodField()
    applicable_events_count = serializers.SerializerMethodField()
    
    # 🚀 ENTERPRISE FIX: Accept both frontend and backend field names
    value = serializers.DecimalField(source='discount_value', max_digits=10, decimal_places=2, required=False)
    discount_value = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, write_only=True)
    
    type = serializers.CharField(source='discount_type', required=False, default='percentage')
    discount_type = serializers.CharField(required=False, default='percentage', write_only=True)
    
    minPurchase = serializers.DecimalField(source='min_purchase', max_digits=10, decimal_places=2, required=False, allow_null=True)
    min_purchase = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, write_only=True)
    
    maxDiscount = serializers.DecimalField(source='max_discount', max_digits=10, decimal_places=2, required=False, allow_null=True)
    max_discount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, write_only=True)
    
    startDate = serializers.DateTimeField(source='start_date', required=False, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True, write_only=True)
    
    endDate = serializers.DateTimeField(source='end_date', required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True, write_only=True)
    
    startTime = serializers.TimeField(source='start_time', required=False, allow_null=True)
    start_time = serializers.TimeField(required=False, allow_null=True, write_only=True)
    
    endTime = serializers.TimeField(source='end_time', required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True, write_only=True)
    
    usage_limit = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    
    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'description', 'type', 'value', 
            'minPurchase', 'maxDiscount', 'startDate', 'endDate',
            'startTime', 'endTime', 'maxUses', 'usedCount', 'status',
            'is_active', 'events', 'ticket_tiers', 'ticket_categories',
            # 🚀 ENTERPRISE: Global vs local coupon fields
            'is_global', 'coupon_scope', 'applicable_events_count',
            # 🚀 ENTERPRISE FIX: Include backend field names for compatibility
            'discount_type', 'discount_value', 'min_purchase', 'max_discount',
            'start_date', 'end_date', 'start_time', 'end_time', 'usage_limit'
        ]
        read_only_fields = ['id', 'usedCount']
    
    def get_events(self, obj) -> Optional[List[str]]:
        """
        Return the applicable events as a list of event IDs or null.
        """
        return obj.get_applicable_events()
    
    def get_is_global(self, obj) -> bool:
        """
        🚀 ENTERPRISE: Return True if coupon is global (applies to all events).
        """
        return obj.events_list is None
    
    def get_coupon_scope(self, obj) -> str:
        """
        🚀 ENTERPRISE: Return human-readable scope description.
        """
        if obj.events_list is None:
            return "🌍 Global - Aplica a todos los eventos"
        elif obj.events_list and len(obj.events_list) == 1:
            return "🎯 Evento específico"
        elif obj.events_list and len(obj.events_list) > 1:
            return f"📋 Múltiples eventos ({len(obj.events_list)} eventos)"
        else:
            return "❓ Scope no definido"
    
    def get_applicable_events_count(self, obj) -> int:
        """
        🚀 ENTERPRISE: Return count of applicable events.
        """
        if obj.events_list is None:
            return -1  # -1 means "all events"
        elif obj.events_list and len(obj.events_list) == 1:
            return 1
        elif obj.events_list and len(obj.events_list) > 1:
            return len(obj.events_list)
        else:
            return 0
    
    def create(self, validated_data):
        """
        Handle creation with proper handling of events list.
        """
        events_data = self.initial_data.get('events')
        
        # Get organizer from the request using OrganizerUser
        from apps.organizers.models import OrganizerUser
        try:
            organizer_user = OrganizerUser.objects.get(user=self.context['request'].user)
            organizer = organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            raise serializers.ValidationError({"detail": "El usuario no tiene un organizador asociado"})
        
        # 🚀 ENTERPRISE FIX: Handle both frontend and backend field names
        # Extract discount_type from either 'type' (frontend) or 'discount_type' (backend)
        discount_type = validated_data.pop('type', validated_data.pop('discount_type', 'percentage'))
        
        # Extract discount_value from either 'value' (frontend) or 'discount_value' (backend)
        discount_value = validated_data.pop('value', validated_data.pop('discount_value', 0))
        
        # Extract usage_limit from either 'maxUses' (frontend) or 'usage_limit' (backend)
        usage_limit = validated_data.pop('maxUses', validated_data.pop('usage_limit', None))
        
        # Extract min_purchase from either 'minPurchase' (frontend) or 'min_purchase' (backend)
        min_purchase = validated_data.pop('minPurchase', validated_data.pop('min_purchase', 0))
        
        # Extract max_discount from either 'maxDiscount' (frontend) or 'max_discount' (backend)
        max_discount = validated_data.pop('maxDiscount', validated_data.pop('max_discount', None))
        
        # Extract start_date from either 'startDate' (frontend) or 'start_date' (backend)
        start_date = validated_data.pop('startDate', validated_data.pop('start_date', None))
        
        # Extract end_date from either 'endDate' (frontend) or 'end_date' (backend)
        end_date = validated_data.pop('endDate', validated_data.pop('end_date', None))
        
        # Extract start_time from either 'startTime' (frontend) or 'start_time' (backend)
        start_time = validated_data.pop('startTime', validated_data.pop('start_time', None))
        
        # Extract end_time from either 'endTime' (frontend) or 'end_time' (backend)
        end_time = validated_data.pop('endTime', validated_data.pop('end_time', None))
        
        # 🚀 ENTERPRISE: Handle events field correctly
        # If events is null -> Global coupon (events_list = null)
        # If events is array -> Local coupon (events_list = events array)
        events_list = None if events_data is None else events_data
        
        # Create the coupon with all fields
        coupon = Coupon.objects.create(
            code=validated_data.get('code', ''),
            description=validated_data.get('description', ''),
            discount_type=discount_type,
            discount_value=discount_value,
            usage_limit=usage_limit,
            min_purchase=min_purchase,
            max_discount=max_discount,
            start_date=start_date,
            end_date=end_date,
            start_time=start_time,
            end_time=end_time,
            events_list=events_list,  # 🚀 ENTERPRISE: Global (null) or Local (array)
            organizer=organizer
        )
        
        return coupon
    
    def update(self, instance, validated_data):
        """
        Handle updates with proper handling of events list.
        """
        events_data = self.initial_data.get('events')
        
        # Update events list
        if events_data is not None:
            instance.events_list = events_data
        
        # Handle nested attributes
        if 'discount_type' in validated_data:
            instance.discount_type = validated_data.pop('discount_type')
        if 'discount_value' in validated_data:
            instance.discount_value = validated_data.pop('discount_value')
        if 'usage_limit' in validated_data:
            instance.usage_limit = validated_data.pop('usage_limit')
        if 'min_purchase' in validated_data:
            instance.min_purchase = validated_data.pop('min_purchase', 0)
        if 'max_discount' in validated_data:
            instance.max_discount = validated_data.pop('max_discount')
        if 'start_date' in validated_data:
            instance.start_date = validated_data.pop('start_date')
        if 'end_date' in validated_data:
            instance.end_date = validated_data.pop('end_date')
        if 'start_time' in validated_data:
            instance.start_time = validated_data.pop('start_time')
        if 'end_time' in validated_data:
            instance.end_time = validated_data.pop('end_time')
        
        # Update remaining fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance





class OrderItemSerializer(serializers.ModelSerializer):
    """
    Serializer for order item model.
    """
    ticket_tier_name = serializers.CharField(source='ticket_tier.name', read_only=True)
    tickets_count = serializers.IntegerField(source='tickets.count', read_only=True)
    attendees = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'ticket_tier', 'ticket_tier_name', 'quantity', 'unit_price',
            'unit_service_fee', 'subtotal', 'tickets_count', 'attendees'
        ]
        read_only_fields = ['id', 'ticket_tier_name', 'subtotal', 'tickets_count', 'attendees']
    
    def get_attendees(self, obj):
        """Return attendees data for this order item."""
        attendees = []
        for ticket in obj.tickets.all():
            attendees.append({
                'name': f"{ticket.first_name} {ticket.last_name}".strip(),
                'email': ticket.email,
                'checkIn': ticket.check_in_status == 'checked_in'
            })
        return attendees


class TicketNoteSerializer(serializers.ModelSerializer):
    """Serializer for ticket notes."""
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    
    class Meta:
        model = TicketNote
        fields = [
            'id', 'content', 'author', 'author_name', 'is_internal', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'author', 'author_name', 'created_at', 'updated_at']


class EmailLogSerializer(serializers.ModelSerializer):
    """Serializer for email logs."""
    recipient = serializers.CharField(source='to_email', read_only=True)
    error_message = serializers.CharField(source='error', read_only=True)
    email_type = serializers.SerializerMethodField()
    
    class Meta:
        model = EmailLog
        fields = [
            'id', 'email_type', 'recipient', 'subject', 'status',
            'sent_at', 'error_message', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_email_type(self, obj):
        """Get email type from template or metadata."""
        if obj.template:
            if 'ticket' in obj.template.lower():
                return 'ticket'
            elif 'reminder' in obj.template.lower():
                return 'reminder'
            elif 'update' in obj.template.lower():
                return 'update'
        return 'custom'


class TicketSerializer(serializers.ModelSerializer):
    """
    🚀 ENTERPRISE: Enhanced serializer for ticket model with approval and check-in workflow.
    """
    attendee_name = serializers.CharField(read_only=True)
    ticket_tier_name = serializers.CharField(source='ticket_tier.name', read_only=True)
    order_number = serializers.CharField(source='order_item.order.order_number', read_only=True)
    
    # Frontend compatibility fields
    name = serializers.SerializerMethodField()
    ticketType = serializers.CharField(source='ticket_type', read_only=True)
    ticketCategory = serializers.CharField(source='ticket_category', read_only=True)
    purchaseDate = serializers.DateTimeField(source='purchase_date', read_only=True)
    checkInStatus = serializers.CharField(source='check_in_status', read_only=True)
    checkInTime = serializers.DateTimeField(source='check_in_time', read_only=True)
    ticketPrice = serializers.DecimalField(source='ticket_price', max_digits=10, decimal_places=2, read_only=True)
    ticketId = serializers.CharField(source='ticket_number', read_only=True)
    requiresApproval = serializers.BooleanField(source='requires_approval', read_only=True)
    approvalStatus = serializers.CharField(source='approval_status', read_only=True)
    approvedBy = serializers.SerializerMethodField()
    approvedAt = serializers.DateTimeField(source='approved_at', read_only=True)
    rejectionReason = serializers.CharField(source='rejection_reason', read_only=True)
    phone = serializers.CharField(read_only=True)
    
    # Notes and email logs
    notes = TicketNoteSerializer(many=True, read_only=True)
    email_logs = EmailLogSerializer(many=True, read_only=True)
    
    class Meta:
        model = Ticket
        fields = [
            'id', 'ticket_number', 'first_name', 'last_name', 'email',
            'status', 'check_in_status', 'check_in_time', 'check_in_by',
            'approval_status', 'approved_by', 'approved_at', 'rejection_reason',
            'form_data', 'attendee_name', 'ticket_tier_name', 'order_number',
            # Frontend compatibility fields
            'name', 'ticketType', 'ticketCategory', 'purchaseDate', 
            'checkInStatus', 'checkInTime', 'ticketPrice', 'ticketId',
            'requiresApproval', 'approvalStatus', 'approvedBy', 'approvedAt',
            'rejectionReason', 'phone',
            # Notes and email logs
            'notes', 'email_logs'
        ]
        read_only_fields = ['id', 'ticket_number', 'attendee_name', 
                           'ticket_tier_name', 'order_number', 'name', 'ticketType',
                           'ticketCategory', 'purchaseDate', 'ticketPrice', 'ticketId',
                           'requiresApproval', 'phone', 'notes', 'email_logs']
    
    def get_name(self, obj):
        """Return full name for frontend compatibility."""
        return obj.attendee_name
    
    def get_approvedBy(self, obj):
        """Return name of user who approved the ticket."""
        if obj.approved_by:
            return f"{obj.approved_by.first_name} {obj.approved_by.last_name}".strip() or obj.approved_by.username
        return None


class OrderSerializer(serializers.ModelSerializer):
    """
    Serializer for order model.
    """
    items = OrderItemSerializer(many=True, read_only=True)
    buyer_name = serializers.CharField(read_only=True)
    event_title = serializers.CharField(source='event.title', read_only=True)
    coupon_code = serializers.CharField(source='coupon.code', read_only=True)
    payment_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'event', 'event_title', 'status', 'email',
            'first_name', 'last_name', 'phone', 'subtotal', 'taxes',
            'service_fee', 'total', 'currency', 'payment_method', 'payment_id',
            'coupon', 'coupon_code', 'discount', 'notes', 'items', 'buyer_name',
            'created_at', 'updated_at', 'refund_reason', 'refunded_amount',
            'payment_details'
        ]
        read_only_fields = ['id', 'order_number', 'buyer_name', 'event_title',
                           'coupon_code', 'created_at', 'updated_at', 'payment_details']
    
    def get_payment_details(self, obj):
        """Get detailed payment information from the payment processor."""
        if Payment is None:
            # Payment processor not available
            return {
                'payment_method': obj.payment_method or 'Método desconocido',
                'payment_status': 'unknown'
            }
        
        try:
            # Get the most recent payment for this order
            payment = obj.payments.order_by('-created_at').first()
            if payment:
                return {
                    'payment_id': str(payment.id),
                    'payment_method': payment.payment_method.display_name if payment.payment_method else 'Método desconocido',
                    'payment_provider': payment.payment_method.provider.name if payment.payment_method and payment.payment_method.provider else 'Desconocido',
                    'payment_status': payment.status,
                    'external_id': payment.external_id,
                    'buy_order': payment.buy_order,
                    'token': payment.token,
                    'metadata': payment.metadata,
                    'authorized_at': payment.authorized_at,
                    'completed_at': payment.completed_at,
                    'expires_at': payment.expires_at
                }
        except Exception as e:
            # Log error but don't fail the serializer
            print(f"Error getting payment details for order {obj.id}: {e}")
        
        # Fallback to basic payment info
        return {
            'payment_method': obj.payment_method or 'Método desconocido',
            'payment_status': 'unknown'
        }


class OrderDetailSerializer(OrderSerializer):
    """
    Detailed serializer for order model including tickets.
    """
    tickets = serializers.SerializerMethodField()
    
    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + ['tickets']
    
    def get_tickets(self, obj):
        tickets = []
        for item in obj.items.all():
            for ticket in item.tickets.all():
                tickets.append(TicketSerializer(ticket).data)
        return tickets


class EventCommunicationSerializer(serializers.ModelSerializer):
    """
    Serializer for event communication model.
    """
    class Meta:
        model = EventCommunication
        fields = [
            'id', 'name', 'type', 'subject', 'content', 'status',
            'scheduled_date', 'sent_date', 'recipients_count',
            'delivery_count', 'open_count', 'click_count'
        ]
        read_only_fields = ['id', 'sent_date', 'recipients_count',
                           'delivery_count', 'open_count', 'click_count']


class OrganizerMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for Organizer model."""
    
    class Meta:
        model = OrganizerUser
        fields = ['id', 'name', 'description', 'logo']


class EventListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing events.
    """
    location = LocationSerializer(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    images = serializers.SerializerMethodField()
    tags_list = serializers.ListField(
        child=serializers.CharField(),
        read_only=True
    )
    ticket_categories_count = serializers.IntegerField(
        source='ticket_categories.count',
        read_only=True
    )
    ticket_tiers_count = serializers.IntegerField(
        source='ticket_tiers.count',
        read_only=True
    )
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'slug', 'short_description', 'status', 'visibility',
            'type', 'template', 'start_date', 'end_date', 'location', 'category_name',
            'organizer_name', 'featured', 'tags_list', 'ticket_categories_count',
            'ticket_tiers_count', 'images'
        ]
        read_only_fields = ['id', 'slug', 'ticket_categories_count', 'ticket_tiers_count']

    def get_images(self, obj) -> List[Dict[str, Any]]:
        """Return event images."""
        request = self.context.get('request')
        images = obj.images.all()[:3]  # Limit to 3 images for list view
        return [
            {
                'id': image.id,
                'url': request.build_absolute_uri(image.image.url),
                'type': image.type,
                'alt': image.alt or obj.title
            } for image in images
        ]


class EventDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for retrieving event details.
    """
    location = LocationSerializer(read_only=True)
    category = EventCategorySerializer(read_only=True)
    images = serializers.SerializerMethodField()
    ticket_tiers = serializers.SerializerMethodField()
    ticket_categories = TicketCategorySerializer(many=True, read_only=True)
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    organizer_logo = serializers.ImageField(source='organizer.logo', read_only=True)
    organizer_description = serializers.CharField(source='organizer.description', read_only=True)
    tags_list = serializers.ListField(
        child=serializers.CharField(),
        read_only=True
    )
    is_active = serializers.BooleanField(read_only=True)
    is_past = serializers.BooleanField(read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    is_ongoing = serializers.BooleanField(read_only=True)
    # Analytics
    views_count = serializers.IntegerField(read_only=True)
    cart_adds_count = serializers.IntegerField(read_only=True)
    conversion_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'slug', 'description', 'short_description',
            'status', 'visibility', 'type', 'template', 'start_date', 'end_date', 
            'location', 'category', 'featured', 'tags', 'tags_list', 
            'organizer_name', 'organizer_logo', 'organizer_description',
            'age_restriction', 'dresscode', 'accessibility', 'parking',
            'max_tickets_per_purchase', 'ticket_sales_start', 'ticket_sales_end',
            'images', 'ticket_tiers', 'ticket_categories', 'is_active', 'is_past', 
            'is_upcoming', 'is_ongoing', 'views_count', 'cart_adds_count', 
            'conversion_count'
        ]
        read_only_fields = ['id', 'slug', 'views_count', 'cart_adds_count', 
                           'conversion_count']

    def get_images(self, obj) -> List[Dict[str, Any]]:
        """Return all event images."""
        request = self.context.get('request')
        return [
            {
                'id': image.id,
                'url': request.build_absolute_uri(image.image.url),
                'type': image.type,
                'alt': image.alt or obj.title
            } for image in obj.images.all()
        ]
    
    def get_ticket_tiers(self, obj) -> List[Dict[str, Any]]:
        """Return public ticket tiers for this event."""
        # Get all public ticket tiers for this event
        public_tiers = obj.ticket_tiers.filter(is_public=True).order_by('order', 'price')
        
        # Use the TicketTierSerializer to serialize each tier
        return TicketTierSerializer(public_tiers, many=True, context=self.context).data


class EventCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating events.
    """
    class Meta:
        model = Event
        fields = [
            'title', 'description', 'short_description', 'status', 'visibility',
            'password', 'type', 'template', 'start_date', 'end_date', 'location', 
            'category', 'featured', 'tags', 'age_restriction', 'dresscode', 
            'accessibility', 'parking', 'max_tickets_per_purchase', 
            'ticket_sales_start', 'ticket_sales_end'
        ]
    
    def create(self, validated_data):
        """
        Create and return a new event instance.
        """
        # Get the current organizer from the request using OrganizerUser
        try:
            organizer_user = OrganizerUser.objects.get(user=self.context['request'].user)
            organizer = organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            raise serializers.ValidationError({"detail": "El usuario no tiene un organizador asociado"})
        
        # Create the event with the organizer
        event = Event.objects.create(
            organizer=organizer,
            **validated_data
        )
        return event


class EventCreateSerializer(serializers.ModelSerializer):
    """Serializer for Event model (creation)."""
    
    location = LocationSerializer(required=False)
    ticket_tiers = TicketTierSerializer(many=True, required=False)
    images = serializers.ListField(
        child=serializers.URLField(),
        required=False,
        write_only=True
    )
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False
    )
    additionalInfo = serializers.DictField(required=False)
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'short_description', 'type',
            'start_date', 'end_date', 'location', 'ticket_tiers',
            'featured', 'tags', 'status', 'images', 'additionalInfo'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        """Validate the event data."""
        # Si el evento está en estado borrador, permitir datos incompletos
        if data.get('status') == 'draft':
            return data
            
        # Para otros estados, verificar que todos los campos obligatorios estén presentes
        required_fields = ['title', 'description', 'short_description', 'start_date', 'end_date']
        
        # Only check location if it's not in draft state
        location_data = data.get('location')
        if not location_data:
            required_fields.append('location')
        
        missing_fields = [field for field in required_fields if field not in data or data.get(field) in [None, '']]
        
        if missing_fields:
            raise serializers.ValidationError({field: "Este campo es requerido." for field in missing_fields})
            
        # Ensure end date is after start date
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({'end_date': 'End date must be after start date'})
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        """Create a new event with related objects."""
        # Get organizer from the request using OrganizerUser
        from apps.organizers.models import OrganizerUser
        try:
            organizer_user = OrganizerUser.objects.get(user=self.context['request'].user)
            organizer = organizer_user.organizer
        except OrganizerUser.DoesNotExist:
            raise serializers.ValidationError({"detail": "El usuario no tiene un organizador asociado"})
        
        # Handle camelCase to snake_case field mapping
        if 'shortDescription' in validated_data:
            validated_data['short_description'] = validated_data.pop('shortDescription')
        
        if 'startDate' in validated_data:
            validated_data['start_date'] = validated_data.pop('startDate')
            
        if 'endDate' in validated_data:
            validated_data['end_date'] = validated_data.pop('endDate')
            
        # Extract nested data
        location_data = validated_data.pop('location', None)
        ticket_tiers_data = validated_data.pop('ticket_tiers', [])
        images_data = validated_data.pop('images', [])
        tags_data = validated_data.pop('tags', [])
        additional_info = validated_data.pop('additionalInfo', {})
        
        # Process tags
        tags_str = ','.join(tags_data) if tags_data else ''
        
        # Create guaranteed unique slug with title + timestamp + random UUID
        title_base = validated_data.get('title', 'evento')
        base_slug = slugify(title_base)
        timestamp = int(timezone.now().timestamp())
        random_id = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID
        slug = f"{base_slug}-{timestamp}-{random_id}"
        
        # Process additional info
        age_restriction = additional_info.get('ageRestriction', '')
        dresscode = additional_info.get('dresscode', '')
        accessibility = ','.join(additional_info.get('accessibility', []))
        parking = additional_info.get('parking', '')
        
        # Find or create location if provided
        location = None
        if location_data:
            location, _ = Location.objects.get_or_create(
                name=location_data.get('name', 'TBD'),
                address=location_data.get('address', 'TBD')
            )
        
        # Find category or use default
        category = None
        if 'category' in validated_data:
            category_name = validated_data.pop('category')
            category, _ = EventCategory.objects.get_or_create(
                name=category_name,
                defaults={'slug': slugify(category_name)}
            )
        
        # Create event with minimal fields for draft state
        event_data = {
            'organizer': organizer,
            'slug': slug,
            'tags': tags_str,
            'age_restriction': age_restriction,
            'dresscode': dresscode,
            'accessibility': accessibility,
            'parking': parking,
            **validated_data
        }
        
        # Only include location if it's available
        if location:
            event_data['location'] = location
        
        # Only include category if it's available    
        if category:
            event_data['category'] = category
        
        # If creating a draft without location, use a default temporary location
        if validated_data.get('status') == 'draft' and not location:
            # Use simplified location lookup with new fields
            try:
                temp_location = Location.objects.filter(
                    name="Ubicación provisional",
                    address="Por definir"
                ).first()
                
                # If no provisional location exists, create one with unique identifier
                if not temp_location:
                    temp_location = Location.objects.create(
                        name="Ubicación provisional",
                        address="Por definir"
                    )
                    
            except Exception as e:
                # Fallback: Create with unique identifier if anything fails
                temp_location = Location.objects.create(
                    name=f"Ubicación provisional {int(timezone.now().timestamp())}",
                    address="Por definir"
                )
                
            event_data['location'] = temp_location
        
        # Create event
        try:
            event = Event.objects.create(**event_data)
            
            # Create ticket tiers if provided
            for tier_data in ticket_tiers_data:
                # Extract nested data
                price_data = tier_data.pop('price', {})
                benefits_data = tier_data.pop('benefits', [])
                metadata = tier_data.pop('metadata', {})
                
                # Create ticket category if needed based on metadata
                ticket_category = None
                if 'category' in metadata:
                    ticket_category, _ = TicketCategory.objects.get_or_create(
                        event=event,
                        name=metadata['category'],
                        defaults={
                            'description': metadata.get('categoryDescription', ''),
                            'capacity': tier_data.get('capacity', 0)
                        }
                    )
                
                # Process benefits
                benefits_str = '\n'.join(benefits_data) if benefits_data else ''
                
                # Create ticket tier
                TicketTier.objects.create(
                    event=event,
                    category=ticket_category,
                    price=price_data.get('basePrice', 0),
                    service_fee=price_data.get('serviceFee', 0),
                    currency=price_data.get('currency', 'CLP'),
                    original_price=price_data.get('originalAmount'),
                    benefits=benefits_str,
                    is_highlighted=metadata.get('isHighlighted', False),
                    is_waitlist=metadata.get('isWaitlist', False),
                    **tier_data
                )
            
            # Create images if provided
            for i, image_url in enumerate(images_data):
                EventImage.objects.create(
                    event=event,
                    image=image_url,  # This assumes the URL is already a local file path
                    alt=f'{event.title or "Evento"} image {i+1}',
                    type='image',
                    order=i)
            
            return event
            
        except Exception as e:
            print(f"Error creating event: {e}")
            raise e


class EventUpdateSerializer(serializers.ModelSerializer):
    """Serializer for Event model (update)."""
    
    location = LocationSerializer(required=False)
    images = serializers.ListField(
        child=serializers.URLField(),
        required=False,
        write_only=True
    )
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False
    )
    additionalInfo = serializers.DictField(required=False)
    
    class Meta:
        model = Event
        fields = [
            'title', 'description', 'short_description', 'type',
            'start_date', 'end_date', 'location', 'featured', 
            'tags', 'status', 'images', 'additionalInfo'
        ]
        partial = True
    
    def validate(self, data):
        """Validate the event data."""
        # Ensure end date is after start date if both are provided
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({'end_date': 'End date must be after start date'})
        
        return data
    
    @transaction.atomic
    def update(self, instance, validated_data):
        """Update an event with related objects."""
        # Add detailed debug logging to see what's happening
        print(f"DEBUG - Event update received for {instance.id}")
        print(f"Raw update data: {validated_data}")
        
        # Extract nested data
        location_data = validated_data.pop('location', None)
        images_data = validated_data.pop('images', None)
        tags_data = validated_data.pop('tags', None)
        additional_info = validated_data.pop('additionalInfo', None)
        
        # Handle camelCase to snake_case field mapping
        if 'shortDescription' in validated_data:
            print(f"Converting shortDescription: '{validated_data['shortDescription']}' to short_description")
            validated_data['short_description'] = validated_data.pop('shortDescription')
        
        if 'startDate' in validated_data:
            print(f"Converting startDate: '{validated_data['startDate']}' to start_date")
            validated_data['start_date'] = validated_data.pop('startDate')
            
        if 'endDate' in validated_data:
            print(f"Converting endDate: '{validated_data['endDate']}' to end_date")
            validated_data['end_date'] = validated_data.pop('endDate')
        
        # After field mapping, show what data will be applied
        print(f"Data to apply after field mapping: {validated_data}")
        
        # Update location if provided with valid data
        if location_data:
            # Check if location data is valid (not empty)
            has_valid_location = (
                location_data.get('name') and 
                location_data.get('address')
            )
            
            if has_valid_location:
                # Create or update location with provided data
                location, _ = Location.objects.update_or_create(
                    id=instance.location.id if instance.location else None,
                    defaults={
                        'name': location_data.get('name', ''),
                        'address': location_data.get('address', '')
                    }
                )
                instance.location = location
            # Keep existing location if location data is invalid (empty fields)
            # This allows moving to the next step without validating location yet
        
        # Update tags if provided
        if tags_data is not None:
            instance.tags = ','.join(tags_data)
        
        # Update additional info if provided
        if additional_info:
            if 'ageRestriction' in additional_info:
                instance.age_restriction = additional_info['ageRestriction']
            if 'dresscode' in additional_info:
                instance.dresscode = additional_info['dresscode']
            if 'accessibility' in additional_info:
                instance.accessibility = ','.join(additional_info['accessibility'])
            if 'parking' in additional_info:
                instance.parking = additional_info['parking']
        
        # Update images if provided
        if images_data is not None:
            # Clear existing images
            instance.images.all().delete()
            
            # Create new images
            for i, image_url in enumerate(images_data):
                EventImage.objects.create(
                    event=instance,
                    image=image_url,  # This assumes the URL is already a local file path
                    alt=f'{instance.title} image {i+1}',
                    type='image',
                    order=i
                )
        
        # Update base fields
        for attr, value in validated_data.items():
            print(f"Setting {attr} = {value}")
            setattr(instance, attr, value)
        
        # Save the instance and print after save
        instance.save()
        print(f"Event after save: title={instance.title}, description={instance.description}, short_description={instance.short_description}")
        
        return instance


class EventAvailabilitySerializer(serializers.Serializer):
    """Serializer for event ticket availability."""
    
    ticketTiers = serializers.SerializerMethodField()
    
    def get_ticketTiers(self, event):
        """Return ticket tiers availability."""
        return [
            {
                'id': tier.id,
                'available': tier.available,
                'total': tier.capacity
            } for tier in event.ticket_tiers.all()
        ]


class BookingSerializer(serializers.Serializer):
    """Serializer for booking event tickets."""
    
    tickets = serializers.ListField(
        child=serializers.DictField(), required=False
    )
    customerInfo = serializers.DictField()
    reservationId = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    def validate(self, data):
        """Validate booking data."""
        event_id = self.context['event_id']
        event = Event.objects.get(id=event_id)
        
        # Check if event is published (available for bookings)
        if event.status != 'published':
            raise serializers.ValidationError({"detail": "This event is not currently available for bookings."})
        
        # Check if event is in the past
        if event.is_past:
            raise serializers.ValidationError({"detail": "Cannot book tickets for past events."})
        
        # Validate tickets (when no reservationId)
        tickets_data = data.get('tickets') or []
        if not data.get('reservationId'):
            for ticket_data in tickets_data:
                tier_id = ticket_data.get('tierId')
                quantity = ticket_data.get('quantity', 0)
                try:
                    tier = TicketTier.objects.get(id=tier_id, event=event)
                except TicketTier.DoesNotExist:
                    raise serializers.ValidationError({"tickets": f"Ticket tier with ID {tier_id} does not exist"})
                if tier.available < quantity:
                    raise serializers.ValidationError({"tickets": f"Not enough tickets available for {tier.name}"})
                if quantity < tier.min_per_order:
                    raise serializers.ValidationError({"tickets": f"Minimum {tier.min_per_order} tickets required for {tier.name}"})
                if quantity > tier.max_per_order:
                    raise serializers.ValidationError({"tickets": f"Maximum {tier.max_per_order} tickets allowed for {tier.name}"})
        
        # Validate customer info
        customer_info = data['customerInfo']
        if not customer_info.get('name'):
            raise serializers.ValidationError({"customerInfo": "Customer name is required"})
        
        if not customer_info.get('email'):
            raise serializers.ValidationError({"customerInfo": "Customer email is required"})
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        """Create a booking order."""
        event_id = self.context['event_id']
        event = Event.objects.get(id=event_id)
        
        # Extract customer info
        customer_info = validated_data['customerInfo']
        name_parts = customer_info['name'].split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        # Calculate totals
        subtotal = 0
        service_fee = 0
        
        # Get user if authenticated, otherwise None for anonymous orders
        user = None
        if hasattr(self.context.get('request'), 'user') and self.context['request'].user.is_authenticated:
            user = self.context['request'].user
        
        # Create order
        order = Order.objects.create(
            event=event,
            user=user,  # Can be None for anonymous orders
            email=customer_info['email'],
            first_name=first_name,
            last_name=last_name,
            phone=customer_info.get('phone', ''),
            subtotal=0,  # Temporary values until calculated
            service_fee=0,
            total=0,
            currency=event.ticket_tiers.first().currency if event.ticket_tiers.exists() else 'CLP',
            status='pending'
        )
        
        # 🚀 ENTERPRISE: Build items either from reservation holds or from payload
        from apps.events.models import TicketHold
        reservation_id = validated_data.get('reservationId') or self.initial_data.get('reservationId')
        items_source = []

        if reservation_id:
            # 🚀 ENTERPRISE: Use holds; do not change availability here (it was adjusted at reserve time)
            holds = TicketHold.objects.select_for_update().filter(order_id=reservation_id, released=False, event=event, expires_at__gt=timezone.now())
            if not holds.exists():
                raise serializers.ValidationError({"detail": "Reservation has expired or is invalid."})
            # aggregate by tier
            by_tier = {}
            for h in holds:
                by_tier[h.ticket_tier_id] = by_tier.get(h.ticket_tier_id, 0) + h.quantity
            items_source = [{ 'tierId': tier_id, 'quantity': qty } for tier_id, qty in by_tier.items()]
        else:
            items_source = validated_data.get('tickets', [])

        # Create order items and tickets
        for ticket_data in items_source:
            tier_id = ticket_data['tierId']
            quantity = int(ticket_data['quantity'])
            tier = TicketTier.objects.get(id=tier_id)
            item_subtotal = tier.price * quantity
            item_service_fee = tier.service_fee * quantity
            subtotal += item_subtotal
            service_fee += item_service_fee
            from apps.events.models import OrderItem
            order_item = OrderItem.objects.create(
                order=order,
                ticket_tier=tier,
                quantity=quantity,
                unit_price=tier.price,
                unit_service_fee=tier.service_fee,
                subtotal=item_subtotal
            )
            # 🚀 ENTERPRISE: Only decrement availability when no reservation was used
            if not reservation_id:
                tier.available -= quantity
                tier.save()
            # Create tickets immediately (for free events or confirmed payments)
            from apps.events.models import Ticket
            for _ in range(quantity):
                Ticket.objects.create(
                    order_item=order_item,
                    first_name=first_name,
                    last_name=last_name,
                    email=customer_info['email'],
                    status='active'
                )
        
        # 🚀 ENTERPRISE: Clean up holds without restocking (tickets already created)
        if reservation_id:
            TicketHold.objects.filter(order_id=reservation_id, event=event).delete()
        
        # Update order totals
        order.subtotal = subtotal
        order.service_fee = service_fee
        order.total = subtotal + service_fee
        
        print(f"🚀 DEBUG - Order totals: subtotal={subtotal}, service_fee={service_fee}, total={order.total}")
        print(f"🚀 DEBUG - Order status before: {order.status}")
        
        # 🚀 ENTERPRISE: Handle payment flow
        if order.total == 0:
            # Free orders: mark as paid immediately and send confirmation
            print(f"🚀 DEBUG - Free order detected! Setting status to 'paid'")
            order.status = 'paid'
            order.save()
            print(f"🚀 DEBUG - Order status after save: {order.status}")
            
            # Send confirmation email for free orders
            try:
                from apps.events.tasks import send_ticket_confirmation_email
                print(f"📧 QUEUE: Enqueuing confirmation email for order {order.id} -> queue 'emails'")
                send_ticket_confirmation_email.apply_async(args=[str(order.id)], queue='emails')
            except Exception as e:
                print(f'Warning: Could not queue confirmation email: {e}')
            
            return {
                'bookingId': str(order.id),
                'status': order.status,
                'totalAmount': float(order.total),
                'payment_required': False,
                'message': 'Reserva confirmada exitosamente'
            }
        else:
            # Paid orders: keep as pending and require payment
            print(f"🚀 DEBUG - Paid order detected! Keeping status as '{order.status}' - Payment required")
            order.save()
            print(f"🚀 DEBUG - Order status after save: {order.status}")
            
            return {
                'bookingId': str(order.id),
                'status': order.status,
                'totalAmount': float(order.total),
                'payment_required': True,
                'message': 'Orden creada exitosamente. Proceder al pago.',
                'next_step': 'payment'
            } 


class TicketTierCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating ticket tiers.
    """
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    service_fee = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    benefits = serializers.ListField(child=serializers.CharField(), required=False)
    
    class Meta:
        model = TicketTier
        fields = [
            'name', 'type', 'description', 'price', 'service_fee',
            'capacity', 'is_public', 'max_per_order', 'min_per_order',
            'benefits', 'category'
        ]
    
    def create(self, validated_data):
        """Create a new ticket tier."""
        benefits_data = validated_data.pop('benefits', [])
        benefits = '\n'.join(benefits_data) if benefits_data else ''
        
        # Create the ticket tier
        tier = TicketTier.objects.create(
            event_id=self.context['event_id'],
            benefits=benefits,
            **validated_data
        )
        
        return tier
    
    def update(self, instance, validated_data):
        """Update an existing ticket tier."""
        benefits_data = validated_data.pop('benefits', None)
        
        # Update benefits if provided
        if benefits_data is not None:
            benefits = '\n'.join(benefits_data) if benefits_data else ''
            instance.benefits = benefits
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance 


class EventSerializer(serializers.ModelSerializer):
    ticket_categories = TicketCategorySerializer(many=True, read_only=True)
    ticket_tiers = TicketTierSerializer(many=True, read_only=True)
    location = LocationSerializer(read_only=True)
    is_simple_event = serializers.ReadOnlyField()
    is_complex_event = serializers.ReadOnlyField()
    simple_available_capacity = serializers.ReadOnlyField()
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'slug', 'description', 'short_description',
            'status', 'visibility', 'password', 'type', 'template',
            'start_date', 'end_date', 'location', 'category', 'featured',
            'tags', 'organizer', 'age_restriction', 'dresscode',
            'accessibility', 'parking', 'max_tickets_per_purchase',
            'ticket_sales_start', 'ticket_sales_end', 'views_count',
            'cart_adds_count', 'conversion_count', 'created_at', 'updated_at',
            'ticket_categories', 'ticket_tiers',
            # New pricing mode fields
            'pricing_mode', 'is_free', 'requires_approval', 
            'simple_capacity', 'simple_price',
            # Computed fields
            'is_simple_event', 'is_complex_event', 'simple_available_capacity'
        ]
        read_only_fields = ['id', 'slug', 'organizer', 'views_count',
                           'cart_adds_count', 'conversion_count', 'created_at', 'updated_at',
                           'is_simple_event', 'is_complex_event', 'simple_available_capacity']


class SimpleBookingSerializer(serializers.ModelSerializer):
    """
    Serializer for simple booking model.
    """
    attendee_name = serializers.ReadOnlyField()
    is_pending = serializers.ReadOnlyField()
    is_confirmed = serializers.ReadOnlyField()
    
    class Meta:
        model = SimpleBooking
        fields = [
            'id', 'event', 'first_name', 'last_name', 'email', 'phone',
            'status', 'notes', 'approved_by', 'approved_at',
            'checked_in', 'check_in_time', 'created_at', 'updated_at',
            'attendee_name', 'is_pending', 'is_confirmed'
        ]
        read_only_fields = ['id', 'approved_by', 'approved_at', 'created_at', 'updated_at',
                           'attendee_name', 'is_pending', 'is_confirmed']


class TicketRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for ticket request model.
    """
    requester_name = serializers.ReadOnlyField()
    is_pending = serializers.ReadOnlyField()
    is_approved = serializers.ReadOnlyField()
    is_rejected = serializers.ReadOnlyField()
    target_name = serializers.ReadOnlyField()
    
    class Meta:
        model = TicketRequest
        fields = [
            'id', 'event', 'ticket_tier', 'ticket_category', 'quantity',
            'first_name', 'last_name', 'email', 'phone', 'message',
            'status', 'reviewed_by', 'reviewed_at', 'review_notes',
            'order', 'simple_booking', 'created_at', 'updated_at',
            'requester_name', 'is_pending', 'is_approved', 'is_rejected', 'target_name'
        ]
        read_only_fields = ['id', 'reviewed_by', 'reviewed_at', 'order', 'simple_booking',
                           'created_at', 'updated_at', 'requester_name', 'is_pending', 
                           'is_approved', 'is_rejected', 'target_name']