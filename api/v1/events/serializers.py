"""Serializers for events API."""

from rest_framework import serializers

from apps.events.models import (
    Event,
    EventCategory,
    Location,
    EventImage,
    TicketTier,
)


class LocationSerializer(serializers.ModelSerializer):
    """
    Serializer for location model.
    """
    class Meta:
        model = Location
        fields = [
            'id', 'name', 'address', 'city', 'country',
            'latitude', 'longitude', 'venue_details', 'capacity'
        ]
        read_only_fields = ['id']


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


class TicketTierSerializer(serializers.ModelSerializer):
    """
    Serializer for ticket tier model.
    """
    benefits_list = serializers.ListField(
        child=serializers.CharField(),
        source='benefits_list',
        read_only=True
    )
    total_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    discount_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    discount_percentage = serializers.IntegerField(read_only=True)
    is_sold_out = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = TicketTier
        fields = [
            'id', 'name', 'type', 'description', 'price', 'service_fee',
            'currency', 'capacity', 'available', 'is_public', 'max_per_order',
            'min_per_order', 'benefits', 'benefits_list', 'original_price',
            'is_early_bird', 'early_bird_deadline', 'is_highlighted',
            'is_waitlist', 'category', 'category_description', 'image',
            'total_price', 'discount_amount', 'discount_percentage',
            'is_sold_out'
        ]
        read_only_fields = ['id']


class EventListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing events.
    """
    location = LocationSerializer(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    tags_list = serializers.ListField(
        child=serializers.CharField(),
        source='tags_list',
        read_only=True
    )
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'slug', 'short_description', 'status', 'type',
            'start_date', 'end_date', 'location', 'category_name',
            'organizer_name', 'featured', 'tags_list'
        ]
        read_only_fields = ['id', 'slug']


class EventDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for retrieving event details.
    """
    location = LocationSerializer(read_only=True)
    category = EventCategorySerializer(read_only=True)
    images = EventImageSerializer(many=True, read_only=True)
    ticket_tiers = TicketTierSerializer(many=True, read_only=True)
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    organizer_logo = serializers.ImageField(source='organizer.logo', read_only=True)
    tags_list = serializers.ListField(
        child=serializers.CharField(),
        source='tags_list',
        read_only=True
    )
    is_active = serializers.BooleanField(read_only=True)
    is_past = serializers.BooleanField(read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    is_ongoing = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'slug', 'description', 'short_description',
            'status', 'type', 'start_date', 'end_date', 'location', 'category',
            'featured', 'tags', 'tags_list', 'organizer_name', 'organizer_logo',
            'age_restriction', 'dresscode', 'accessibility', 'parking',
            'max_tickets_per_purchase', 'ticket_sales_start', 'ticket_sales_end',
            'images', 'ticket_tiers', 'is_active', 'is_past', 'is_upcoming',
            'is_ongoing'
        ]
        read_only_fields = ['id', 'slug']


class EventCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating events.
    """
    class Meta:
        model = Event
        fields = [
            'title', 'description', 'short_description', 'status', 'type',
            'start_date', 'end_date', 'location', 'category', 'featured',
            'tags', 'age_restriction', 'dresscode', 'accessibility', 'parking',
            'max_tickets_per_purchase', 'ticket_sales_start', 'ticket_sales_end'
        ]
    
    def create(self, validated_data):
        """
        Create and return a new event instance.
        """
        # Get the current organizer from the request
        organizer = self.context['request'].user.organizer
        
        # Create the event with the organizer
        event = Event.objects.create(
            organizer=organizer,
            **validated_data
        )
        
        return event 