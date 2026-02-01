"""Serializers for experiences API."""

from rest_framework import serializers
from django.utils import timezone
from django.utils.text import slugify
from django.db import transaction
from django.contrib.auth import get_user_model
from datetime import timedelta

from .models import (
    Experience, TourLanguage, TourInstance, TourBooking, OrganizerCredit,
    ExperienceResource, ExperienceReservation, ExperienceDatePriceOverride,
    ExperienceCapacityHold, ExperienceResourceHold
)
from apps.organizers.models import OrganizerUser
from apps.events.models import Order

User = get_user_model()


class ExperienceSerializer(serializers.ModelSerializer):
    """
    🚀 ENTERPRISE: Serializer for Experience model with robust validation.
    
    Includes comprehensive field validation with clear, actionable error messages.
    """
    
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    country_name = serializers.SerializerMethodField()
    
    def get_country_name(self, obj):
        """Get country name, returning None if country is not set."""
        return obj.country.name if obj.country else None
    
    class Meta:
        model = Experience
        fields = [
            'id', 'title', 'slug', 'description', 'short_description', 'status', 'type',
            'organizer', 'organizer_name', 'pricing_mode', 'price', 'child_price', 'is_child_priced',
            'infant_price', 'is_infant_priced', 'currency', 'is_free_tour', 'credit_per_person',
            'is_whatsapp_reservation', 'capacity_count_rule', 'booking_horizon_days', 'sales_cutoff_hours',
            'recurrence_pattern', 'location_name', 'location_address', 'location_latitude', 'location_longitude',
            'country', 'country_name', 'duration_minutes', 'max_participants', 'min_participants', 'included', 'not_included',
            'requirements', 'itinerary', 'images', 'categories', 'tags', 'views_count',
            'is_active', 'deleted_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'organizer', 'created_at', 'updated_at', 'views_count', 'deleted_at']
    
    def validate_title(self, value):
        """Validate title is not empty and has reasonable length."""
        if not value or not value.strip():
            raise serializers.ValidationError("El título es requerido y no puede estar vacío.")
        if len(value.strip()) < 3:
            raise serializers.ValidationError("El título debe tener al menos 3 caracteres.")
        if len(value) > 200:
            raise serializers.ValidationError("El título no puede exceder 200 caracteres.")
        return value.strip()
    
    def validate_description(self, value):
        """Validate description is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("La descripción es requerida y no puede estar vacía.")
        if len(value.strip()) < 10:
            raise serializers.ValidationError("La descripción debe tener al menos 10 caracteres.")
        return value.strip()
    
    def validate_location_name(self, value):
        """Validate location name is provided."""
        if not value or not value.strip():
            raise serializers.ValidationError("El nombre del lugar es requerido.")
        return value.strip()
    
    def validate_location_address(self, value):
        """Validate location address is provided."""
        if not value or not value.strip():
            raise serializers.ValidationError("La dirección es requerida.")
        return value.strip()
    
    def validate_duration_minutes(self, value):
        """Validate duration is positive."""
        if value is not None and value <= 0:
            raise serializers.ValidationError("La duración debe ser mayor a 0 minutos.")
        return value
    
    def validate_price(self, value):
        """Validate price is non-negative."""
        if value is not None and value < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")
        return value
    
    def validate_min_participants(self, value):
        """Validate min participants is positive."""
        if value is not None and value <= 0:
            raise serializers.ValidationError("El número mínimo de participantes debe ser mayor a 0.")
        return value
    
    def validate_max_participants(self, value):
        """Validate max participants is greater than min."""
        min_participants = self.initial_data.get('min_participants')
        if value is not None and min_participants is not None:
            if value < min_participants:
                raise serializers.ValidationError(
                    f"El número máximo de participantes ({value}) no puede ser menor "
                    f"que el número mínimo ({min_participants})."
                )
        return value
    
    def validate(self, attrs):
        """
        🚀 ENTERPRISE: Cross-field validation with clear error messages.
        
        🔧 FIX: For partial updates (PATCH), use existing instance values when
        fields are not being updated to avoid false validation errors.
        """
        errors = {}
        
        # 🔧 FIX: For partial updates, get values from instance if not in attrs
        is_free_tour = attrs.get('is_free_tour')
        if is_free_tour is None and self.instance:
            # Partial update: use existing value from instance
            is_free_tour = self.instance.is_free_tour
        elif is_free_tour is None:
            # New creation: default to False
            is_free_tour = False
        
        # Validate free tour requirements
        if is_free_tour:
            credit_per_person = attrs.get('credit_per_person')
            if credit_per_person is None and self.instance:
                # Partial update: use existing value from instance
                credit_per_person = self.instance.credit_per_person
            # Only validate credit_per_person if it's being updated or it's a new creation
            if 'credit_per_person' in attrs or not self.instance:
                if credit_per_person is None or credit_per_person <= 0:
                    errors['credit_per_person'] = [
                        "El crédito por persona es requerido para tours gratuitos y debe ser mayor a 0."
                    ]
        
        # Validate pricing for paid tours
        if not is_free_tour:
            price = attrs.get('price')
            if price is None and self.instance:
                # Partial update: use existing value from instance
                price = self.instance.price
            elif price is None:
                # New creation: default to 0
                price = 0
            # Only validate price if it's being updated or it's a new creation
            if 'price' in attrs or not self.instance:
                if price is None or price <= 0:
                    errors['price'] = [
                        "El precio es requerido para tours pagados y debe ser mayor a 0."
                    ]
        
        # Validate participants range
        min_participants = attrs.get('min_participants')
        max_participants = attrs.get('max_participants')
        if min_participants and max_participants:
            if max_participants < min_participants:
                errors['max_participants'] = [
                    f"El máximo ({max_participants}) no puede ser menor que el mínimo ({min_participants})."
                ]
        
        if errors:
            raise serializers.ValidationError(errors)
        
        return attrs
    
    def create(self, validated_data):
        """
        🚀 ENTERPRISE: Create experience with slug generation, error handling, and auto-create TourOperator.
        
        Uses ExperienceOperatorService for modular operator and binding management.
        """
        import logging
        from apps.whatsapp.services.experience_operator_service import ExperienceOperatorService
        
        logger = logging.getLogger(__name__)
        
        try:
            # Generate unique slug
            if 'slug' not in validated_data or not validated_data['slug']:
                validated_data['slug'] = slugify(validated_data['title'])
                base_slug = validated_data['slug']
                counter = 1
                while Experience.objects.filter(slug=validated_data['slug']).exists():
                    validated_data['slug'] = f"{base_slug}-{counter}"
                    counter += 1
            
            organizer = validated_data.get('organizer')
            
            # Auto-create TourOperator if organizer exists
            tour_operator = None
            if organizer:
                try:
                    tour_operator, _ = ExperienceOperatorService.get_or_create_operator_for_organizer(organizer)
                except Exception as e:
                    logger.warning(f"Could not create/get TourOperator for organizer: {e}")
                    # Continue without operator - experience can still be created
            
            # Create the experience
            experience = super().create(validated_data)
            
            # Create ExperienceGroupBinding if operator has default group
            if tour_operator:
                try:
                    ExperienceOperatorService.create_experience_group_binding(
                        experience=experience,
                        tour_operator=tour_operator,
                        is_override=False
                    )
                except Exception as e:
                    logger.warning(f"Could not create ExperienceGroupBinding: {e}")
                    # Continue - binding can be created later
            
            return experience
        except serializers.ValidationError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            logger.error(f"🔴 [EXPERIENCE_SERIALIZER] Error creating experience: {str(e)}", exc_info=True)
            raise serializers.ValidationError({
                'non_field_errors': [f"Error al crear la experiencia: {str(e)}"]
            })


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
            'language', 'status', 'max_capacity', 'override_adult_price', 'override_child_price',
            'override_infant_price', 'notes', 'current_bookings_count', 'available_spots',
            'created_at', 'updated_at'
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
        # 🚀 ENTERPRISE: Use generalized Order model with order_kind='experience'
        order = Order.objects.create(
            event=None,  # No event for tour bookings
            user=user,
            total=0,
            subtotal=0,
            service_fee=0,
            discount=0,
            taxes=0,
            order_kind='experience',
            status='paid',  # Free tours are immediately treated as paid (total = 0)
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


class ExperienceResourceSerializer(serializers.ModelSerializer):
    """Serializer for ExperienceResource model."""
    
    class Meta:
        model = ExperienceResource
        fields = [
            'id', 'experience', 'name', 'description', 'resource_type', 'group_id',
            'price', 'is_per_person', 'people_per_unit', 'available_quantity',
            'image_url', 'display_order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ExperienceDatePriceOverrideSerializer(serializers.ModelSerializer):
    """Serializer for ExperienceDatePriceOverride model."""
    
    class Meta:
        model = ExperienceDatePriceOverride
        fields = [
            'id', 'experience', 'date', 'start_time', 'end_time',
            'override_adult_price', 'override_child_price', 'override_infant_price',
            'override_capacity', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ExperienceReservationSerializer(serializers.ModelSerializer):
    """Serializer for ExperienceReservation model."""
    
    experience_title = serializers.CharField(source='experience.title', read_only=True)
    instance_info = serializers.SerializerMethodField()
    
    class Meta:
        model = ExperienceReservation
        fields = [
            'id', 'reservation_id', 'experience', 'experience_title', 'instance', 'instance_info',
            'status', 'adult_count', 'child_count', 'infant_count', 'first_name', 'last_name',
            'email', 'phone', 'user', 'subtotal', 'service_fee', 'discount', 'total', 'currency',
            'pricing_details', 'selected_resources', 'capacity_count_rule', 'expires_at', 'paid_at',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reservation_id', 'created_at', 'updated_at']
    
    def get_instance_info(self, obj):
        """Get instance summary."""
        if obj.instance:
            return {
                'id': str(obj.instance.id),
                'start_datetime': obj.instance.start_datetime.isoformat(),
                'end_datetime': obj.instance.end_datetime.isoformat(),
                'language': obj.instance.language,
            }
        return None

