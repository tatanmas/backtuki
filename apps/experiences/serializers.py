"""Serializers for experiences API."""

from rest_framework import serializers
from django.utils import timezone
from django.utils.text import slugify
from django.db import transaction
from django.contrib.auth import get_user_model
from datetime import timedelta

from .models import Experience, TourLanguage, TourInstance, TourBooking, OrganizerCredit
from apps.organizers.models import OrganizerUser
from apps.events.models import Order

User = get_user_model()


class ExperienceSerializer(serializers.ModelSerializer):
    """Serializer for Experience model."""
    
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    
    class Meta:
        model = Experience
        fields = [
            'id', 'title', 'slug', 'description', 'short_description', 'status', 'type',
            'organizer', 'organizer_name', 'price', 'is_free_tour', 'credit_per_person',
            'sales_cutoff_hours', 'recurrence_pattern', 'location_name', 'location_address',
            'location_latitude', 'location_longitude', 'duration_minutes', 'max_participants',
            'min_participants', 'included', 'not_included', 'requirements', 'itinerary',
            'images', 'categories', 'tags', 'views_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'views_count']
    
    def create(self, validated_data):
        """Create experience with slug generation."""
        if 'slug' not in validated_data or not validated_data['slug']:
            validated_data['slug'] = slugify(validated_data['title'])
            # Ensure unique slug
            base_slug = validated_data['slug']
            counter = 1
            while Experience.objects.filter(slug=validated_data['slug']).exists():
                validated_data['slug'] = f"{base_slug}-{counter}"
                counter += 1
        return super().create(validated_data)


class TourLanguageSerializer(serializers.ModelSerializer):
    """Serializer for TourLanguage model."""
    
    experience_title = serializers.CharField(source='experience.title', read_only=True)
    
    class Meta:
        model = TourLanguage
        fields = [
            'id', 'experience', 'experience_title', 'language_code', 'title',
            'description', 'short_description', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TourInstanceSerializer(serializers.ModelSerializer):
    """Serializer for TourInstance model."""
    
    experience_title = serializers.CharField(source='experience.title', read_only=True)
    current_bookings_count = serializers.SerializerMethodField()
    available_spots = serializers.SerializerMethodField()
    
    class Meta:
        model = TourInstance
        fields = [
            'id', 'experience', 'experience_title', 'start_datetime', 'end_datetime',
            'language', 'status', 'max_capacity', 'notes', 'current_bookings_count',
            'available_spots', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'current_bookings_count', 'available_spots']
    
    def get_current_bookings_count(self, obj):
        """Get current bookings count."""
        return obj.get_current_bookings_count()
    
    def get_available_spots(self, obj):
        """Get available spots."""
        return obj.get_available_spots()


class TourBookingSerializer(serializers.ModelSerializer):
    """Serializer for TourBooking model."""
    
    tour_instance_info = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = TourBooking
        fields = [
            'id', 'tour_instance', 'tour_instance_info', 'user', 'user_email',
            'first_name', 'last_name', 'email', 'phone', 'participants_count',
            'status', 'order', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_tour_instance_info(self, obj):
        """Get tour instance summary."""
        if obj.tour_instance:
            return {
                'id': str(obj.tour_instance.id),
                'start_datetime': obj.tour_instance.start_datetime.isoformat(),
                'language': obj.tour_instance.language,
                'experience_title': obj.tour_instance.experience.title
            }
        return None


class TourBookingCreateSerializer(serializers.Serializer):
    """Serializer for creating tour bookings (with user account linking)."""
    
    tour_instance_id = serializers.UUIDField()
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    participants_count = serializers.IntegerField(min_value=1, default=1)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_tour_instance_id(self, value):
        """Validate tour instance exists and is available."""
        try:
            tour_instance = TourInstance.objects.get(id=value)
        except TourInstance.DoesNotExist:
            raise serializers.ValidationError("Tour instance not found.")
        
        if tour_instance.status != 'active':
            raise serializers.ValidationError("Tour instance is not active.")
        
        # Check if booking is within sales cutoff
        if tour_instance.experience.is_free_tour:
            cutoff_time = tour_instance.start_datetime - timedelta(
                hours=tour_instance.experience.sales_cutoff_hours
            )
            if timezone.now() > cutoff_time:
                raise serializers.ValidationError(
                    f"Booking is closed. Sales cutoff is {tour_instance.experience.sales_cutoff_hours} hours before tour start."
                )
        
        # Check capacity
        available = tour_instance.get_available_spots()
        if available is not None and available < 1:
            raise serializers.ValidationError("Tour instance is fully booked.")
        
        return value
    
    @transaction.atomic
    def create(self, validated_data):
        """Create tour booking with user account linking."""
        tour_instance = TourInstance.objects.get(id=validated_data['tour_instance_id'])
        email = validated_data['email']
        
        # 🚀 ENTERPRISE: User account linking (reuse logic from tickets)
        user = None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Create guest user account
            user = User.create_guest_user(
                email=email,
                first_name=validated_data['first_name'],
                last_name=validated_data['last_name']
            )
        
        # Create Order with amount=0 (for tracking)
        order = Order.objects.create(
            event=None,  # No event for tour bookings
            user=user,
            total=0,
            subtotal=0,
            service_fee=0,
            status='completed'  # Free tours are immediately completed
        )
        
        # Create TourBooking
        booking = TourBooking.objects.create(
            tour_instance=tour_instance,
            user=user,
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            email=email,
            phone=validated_data.get('phone', ''),
            participants_count=validated_data['participants_count'],
            status='confirmed',
            order=order,
            notes=validated_data.get('notes', '')
        )
        
        # Create OrganizerCredit if it's a free tour
        if tour_instance.experience.is_free_tour:
            credit_amount = tour_instance.experience.credit_per_person * validated_data['participants_count']
            OrganizerCredit.objects.create(
                organizer=tour_instance.experience.organizer,
                tour_booking=booking,
                amount=credit_amount,
                is_billed=False
            )
        
        return booking


class OrganizerCreditSerializer(serializers.ModelSerializer):
    """Serializer for OrganizerCredit model."""
    
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    booking_info = serializers.SerializerMethodField()
    
    class Meta:
        model = OrganizerCredit
        fields = [
            'id', 'organizer', 'organizer_name', 'tour_booking', 'booking_info',
            'amount', 'is_billed', 'billed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_booking_info(self, obj):
        """Get booking summary."""
        if obj.tour_booking:
            return {
                'id': str(obj.tour_booking.id),
                'customer_name': f"{obj.tour_booking.first_name} {obj.tour_booking.last_name}",
                'participants_count': obj.tour_booking.participants_count
            }
        return None

