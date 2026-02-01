"""Serializers for terminal API."""

from rest_framework import serializers
from .models import (
    TerminalCompany, TerminalRoute, TerminalTrip, TerminalExcelUpload,
    TerminalDestination, TerminalAdvertisingSpace, TerminalAdvertisingInteraction,
    TerminalDestinationExperienceConfig
)


class TerminalCompanySerializer(serializers.ModelSerializer):
    """Serializer for TerminalCompany."""
    
    class Meta:
        model = TerminalCompany
        fields = [
            'id', 'name', 'logo', 'phone', 'email', 'website',
            'contact_method', 'booking_url', 'booking_phone',
            'booking_whatsapp', 'booking_method', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TerminalRouteSerializer(serializers.ModelSerializer):
    """Serializer for TerminalRoute."""
    
    class Meta:
        model = TerminalRoute
        fields = ['id', 'origin', 'destination', 'duration', 'distance', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class TerminalTripSerializer(serializers.ModelSerializer):
    """Serializer for TerminalTrip."""
    
    company = TerminalCompanySerializer(read_only=True)
    route = TerminalRouteSerializer(read_only=True)
    company_id = serializers.UUIDField(write_only=True, required=False)
    route_id = serializers.UUIDField(write_only=True, required=False)
    
    # Format times as "HH:MM" strings
    departure_time = serializers.TimeField(format='%H:%M', required=False, allow_null=True)
    arrival_time = serializers.TimeField(format='%H:%M', required=False, allow_null=True)
    
    class Meta:
        model = TerminalTrip
        fields = [
            'id', 'company', 'company_id', 'route', 'route_id',
            'trip_type', 'date', 'departure_time', 'arrival_time',
            'platform', 'license_plate', 'observations',
            'total_seats', 'available_seats', 'status', 'price',
            'currency', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Validate trip data based on trip_type."""
        trip_type = data.get('trip_type')
        
        if trip_type == 'departure':
            if not data.get('departure_time'):
                raise serializers.ValidationError({
                    'departure_time': 'Departure time is required for departure trips.'
                })
            if data.get('arrival_time'):
                raise serializers.ValidationError({
                    'arrival_time': 'Arrival time should not be set for departure trips.'
                })
        elif trip_type == 'arrival':
            if not data.get('arrival_time'):
                raise serializers.ValidationError({
                    'arrival_time': 'Arrival time is required for arrival trips.'
                })
            if data.get('departure_time'):
                raise serializers.ValidationError({
                    'departure_time': 'Departure time should not be set for arrival trips.'
                })
        
        return data


class TerminalExcelUploadSerializer(serializers.ModelSerializer):
    """Serializer for TerminalExcelUpload."""
    
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)
    
    class Meta:
        model = TerminalExcelUpload
        fields = [
            'id', 'file_name', 'file_path', 'upload_type',
            'date_range_start', 'date_range_end', 'processed_sheets',
            'trips_created', 'trips_updated', 'errors', 'status',
            'uploaded_by', 'uploaded_by_email', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'file_path', 'processed_sheets', 'trips_created',
            'trips_updated', 'errors', 'status', 'created_at', 'updated_at'
        ]


class TerminalDestinationSerializer(serializers.ModelSerializer):
    """Serializer for TerminalDestination."""
    
    class Meta:
        model = TerminalDestination
        fields = [
            'id', 'name', 'slug', 'description', 'image', 'region',
            'is_active', 'created_from_excel', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']


class ExperienceNestedSerializer(serializers.Serializer):
    """Nested serializer for Experience data in advertising spaces."""
    
    id = serializers.UUIDField()
    title = serializers.CharField()
    slug = serializers.SlugField()
    description = serializers.CharField()
    short_description = serializers.CharField(required=False, allow_null=True)
    images = serializers.ListField(child=serializers.URLField(), required=False, allow_empty=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    location_name = serializers.CharField(required=False, allow_null=True)
    duration_minutes = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.CharField()
    type = serializers.CharField()
    
    def to_representation(self, instance):
        """Convert Experience instance to nested representation."""
        if instance is None:
            return None
        return {
            'id': str(instance.id),
            'title': instance.title,
            'slug': instance.slug,
            'description': instance.description or '',
            'short_description': instance.short_description or None,
            'images': instance.images or [],
            'price': float(instance.price),
            'currency': instance.currency,
            'location_name': instance.location_name or None,
            'duration_minutes': instance.duration_minutes,
            'status': instance.status,
            'type': instance.type,
        }


class TerminalAdvertisingSpaceSerializer(serializers.ModelSerializer):
    """Serializer for TerminalAdvertisingSpace."""
    
    destination = TerminalDestinationSerializer(read_only=True)
    destination_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    experience = serializers.SerializerMethodField()
    experience_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = TerminalAdvertisingSpace
        fields = [
            'id', 'space_type', 'position', 'destination', 'destination_id',
            'route_origin', 'route_destination', 'content_type', 'experience',
            'experience_id', 'banner_image', 'banner_title', 'banner_subtitle',
            'banner_cta_text', 'banner_cta_url', 'order', 'is_active',
            'display_from', 'display_until', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_experience(self, obj):
        """Get nested experience data if exists."""
        if obj.experience:
            serializer = ExperienceNestedSerializer()
            return serializer.to_representation(obj.experience)
        return None
    
    def validate(self, data):
        """Validate that content_type matches the provided data."""
        content_type = data.get('content_type')
        
        if content_type == 'experience':
            if not data.get('experience_id'):
                raise serializers.ValidationError({
                    'experience_id': 'Experience ID is required when content_type is "experience".'
                })
        elif content_type == 'banner':
            if not data.get('banner_image') and not self.instance:
                raise serializers.ValidationError({
                    'banner_image': 'Banner image is required when content_type is "banner".'
                })
        
        return data
    
    def create(self, validated_data):
        """Create advertising space with proper foreign key handling."""
        destination_id = validated_data.pop('destination_id', None)
        experience_id = validated_data.pop('experience_id', None)
        
        if destination_id:
            from .models import TerminalDestination
            validated_data['destination'] = TerminalDestination.objects.get(id=destination_id)
        
        if experience_id:
            from apps.experiences.models import Experience
            validated_data['experience'] = Experience.objects.get(id=experience_id)
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Update advertising space with proper foreign key handling."""
        destination_id = validated_data.pop('destination_id', None)
        experience_id = validated_data.pop('experience_id', None)
        
        if destination_id is not None:
            from .models import TerminalDestination
            if destination_id:
                validated_data['destination'] = TerminalDestination.objects.get(id=destination_id)
            else:
                validated_data['destination'] = None
        
        if experience_id is not None:
            from apps.experiences.models import Experience
            if experience_id:
                validated_data['experience'] = Experience.objects.get(id=experience_id)
            else:
                validated_data['experience'] = None
        
        return super().update(instance, validated_data)


class TerminalAdvertisingInteractionSerializer(serializers.ModelSerializer):
    """Serializer for TerminalAdvertisingInteraction."""
    
    advertising_space = TerminalAdvertisingSpaceSerializer(read_only=True)
    advertising_space_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = TerminalAdvertisingInteraction
        fields = [
            'id', 'advertising_space', 'advertising_space_id',
            'interaction_type', 'user_ip', 'user_agent', 'referrer',
            'destination', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TerminalDestinationExperienceConfigSerializer(serializers.ModelSerializer):
    """Serializer for TerminalDestinationExperienceConfig."""
    
    destination = TerminalDestinationSerializer(read_only=True)
    destination_id = serializers.UUIDField(write_only=True)
    experience = serializers.SerializerMethodField()
    experience_id = serializers.UUIDField(write_only=True)
    
    class Meta:
        model = TerminalDestinationExperienceConfig
        fields = [
            'id', 'destination', 'destination_id', 'experience', 'experience_id',
            'is_featured', 'order', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_experience(self, obj):
        """Get nested experience data if exists."""
        if obj.experience:
            serializer = ExperienceNestedSerializer()
            return serializer.to_representation(obj.experience)
        return None
    
    def create(self, validated_data):
        """Create config with proper foreign key handling."""
        destination_id = validated_data.pop('destination_id')
        experience_id = validated_data.pop('experience_id')
        
        from .models import TerminalDestination
        from apps.experiences.models import Experience
        
        validated_data['destination'] = TerminalDestination.objects.get(id=destination_id)
        validated_data['experience'] = Experience.objects.get(id=experience_id)
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Update config with proper foreign key handling."""
        destination_id = validated_data.pop('destination_id', None)
        experience_id = validated_data.pop('experience_id', None)
        
        if destination_id:
            from .models import TerminalDestination
            validated_data['destination'] = TerminalDestination.objects.get(id=destination_id)
        
        if experience_id:
            from apps.experiences.models import Experience
            validated_data['experience'] = Experience.objects.get(id=experience_id)
        
        return super().update(instance, validated_data)

