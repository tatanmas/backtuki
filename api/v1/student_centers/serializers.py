"""Serializers for student centers API."""

from rest_framework import serializers
from apps.organizers.models import StudentCenterConfig, Organizer
from apps.experiences.models import StudentCenterTimelineItem, StudentInterest, Experience


class StudentCenterConfigSerializer(serializers.ModelSerializer):
    """Serializer for student center configuration."""
    
    banner_image_url_display = serializers.SerializerMethodField(read_only=True)
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    organizer_slug = serializers.CharField(source='organizer.slug', read_only=True)
    
    class Meta:
        model = StudentCenterConfig
        fields = [
            'id', 'organizer', 'organizer_name', 'organizer_slug',
            'banner_image', 'banner_image_url', 'banner_image_url_display', 'banner_text', 'is_active',
            'selected_experiences', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'banner_image': {'required': False, 'allow_null': True},
            'banner_image_url': {'required': False, 'allow_null': True}
        }
    
    def get_banner_image_url_display(self, obj):
        """Get the full URL for the banner image (for display purposes)."""
        # Prefer banner_image_url (from media library) over banner_image (uploaded file)
        if obj.banner_image_url:
            return obj.banner_image_url
        if obj.banner_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None
    
    def to_representation(self, instance):
        """Override to include banner_image_url_display as banner_image_url for backward compatibility."""
        data = super().to_representation(instance)
        # Use banner_image_url_display as banner_image_url in response
        if 'banner_image_url_display' in data:
            data['banner_image_url'] = data.pop('banner_image_url_display')
        return data


class ExperienceSelectionSerializer(serializers.ModelSerializer):
    """Simplified serializer for experience selection in student center."""
    
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    first_image = serializers.SerializerMethodField()
    
    class Meta:
        model = Experience
        fields = [
            'id', 'title', 'slug', 'short_description', 'description',
            'type', 'status', 'organizer', 'organizer_name',
            'duration_minutes', 'min_participants', 'max_participants',
            'location_name', 'location_address', 'first_image',
            'price', 'is_free_tour', 'included', 'not_included',
            'requirements', 'itinerary', 'created_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at']
    
    def get_first_image(self, obj):
        """Get the first image URL if available."""
        if obj.images and len(obj.images) > 0:
            request = self.context.get('request')
            if request and isinstance(obj.images[0], str):
                # If it's already a URL, return as is
                if obj.images[0].startswith('http'):
                    return obj.images[0]
                # Otherwise build absolute URL
                return request.build_absolute_uri(obj.images[0])
            return obj.images[0]
        return None


class StudentInterestSerializer(serializers.ModelSerializer):
    """Serializer for student interest registration."""
    
    timeline_item_title = serializers.CharField(source='timeline_item.experience.title', read_only=True)
    
    class Meta:
        model = StudentInterest
        fields = [
            'id', 'timeline_item', 'timeline_item_title',
            'name', 'email', 'phone', 'status',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'timeline_item': {'required': False},  # Set automatically in view
            'name': {'required': True},
            'email': {'required': True},
            'phone': {'required': False, 'allow_null': True},
            'status': {'required': False},
        }
    
    def validate_email(self, value):
        """Validate email format and normalize."""
        if not value:
            raise serializers.ValidationError("El email es requerido.")
        # Normalize email (lowercase, strip whitespace)
        return value.lower().strip()
    
    def validate_name(self, value):
        """Validate name is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("El nombre es requerido.")
        return value.strip()


class PublicStudentInterestSerializer(serializers.ModelSerializer):
    """
    🚀 ENTERPRISE: Serializer for public student interest registration.
    
    This serializer excludes timeline_item from validation as it's provided via URL parameter.
    Used for public endpoints where timeline_item is set automatically by the view.
    """
    
    class Meta:
        model = StudentInterest
        fields = ['name', 'email', 'phone']
        extra_kwargs = {
            'name': {'required': True},
            'email': {'required': True},
            'phone': {'required': False, 'allow_null': True, 'allow_blank': True},
        }
    
    def validate_email(self, value):
        """Validate email format and normalize."""
        if not value:
            raise serializers.ValidationError("El email es requerido.")
        # Normalize email (lowercase, strip whitespace)
        normalized = value.lower().strip()
        # Basic email format validation
        if '@' not in normalized or '.' not in normalized.split('@')[1]:
            raise serializers.ValidationError("El email no tiene un formato válido.")
        return normalized
    
    def validate_name(self, value):
        """Validate name is not empty and has reasonable length."""
        if not value or not value.strip():
            raise serializers.ValidationError("El nombre es requerido.")
        name = value.strip()
        if len(name) < 2:
            raise serializers.ValidationError("El nombre debe tener al menos 2 caracteres.")
        if len(name) > 255:
            raise serializers.ValidationError("El nombre no puede exceder 255 caracteres.")
        return name
    
    def validate_phone(self, value):
        """Validate phone format if provided."""
        if value:
            # Remove common formatting characters for validation
            cleaned = value.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')
            # Check if it's mostly digits (allowing + prefix)
            if not cleaned.replace('+', '').isdigit():
                raise serializers.ValidationError("El teléfono debe contener solo números y caracteres de formato (+ - espacios).")
        return value


class StudentCenterTimelineItemSerializer(serializers.ModelSerializer):
    """Serializer for student center timeline item."""
    
    experience_data = ExperienceSelectionSerializer(source='experience', read_only=True)
    interested_count = serializers.SerializerMethodField()
    can_confirm = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = StudentCenterTimelineItem
        fields = [
            'id', 'student_center', 'experience', 'experience_data',
            'scheduled_date', 'duration_minutes', 'min_participants',
            'max_participants', 'interest_threshold', 'status', 'status_display',
            'display_order', 'interested_count', 'can_confirm',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'student_center': {'required': False},  # Set automatically in viewset
            'experience': {'required': True},
            'scheduled_date': {'required': False, 'allow_null': True},
            'duration_minutes': {'required': False, 'allow_null': True},
            'min_participants': {'required': False, 'allow_null': True},
            'max_participants': {'required': False, 'allow_null': True},
            'interest_threshold': {'required': False},
            'status': {'required': False},
            'display_order': {'required': False, 'allow_null': True},
        }
    
    def get_interested_count(self, obj):
        """Get the count of interested students."""
        return obj.get_interested_count()
    
    def get_can_confirm(self, obj):
        """Check if this item can be confirmed."""
        return obj.can_confirm()

