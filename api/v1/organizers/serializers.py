"""Serializers for organizers API."""

from rest_framework import serializers

from apps.organizers.models import (
    Organizer,
    OrganizerUser,
    OrganizerSubscription,
    OrganizerOnboarding,
    BillingDetails,
    BankingDetails,
)


class OrganizerSerializer(serializers.ModelSerializer):
    """
    Serializer for organizer model.
    """
    class Meta:
        model = Organizer
        fields = [
            'id', 'name', 'slug', 'description', 'logo',
            'website', 'contact_email', 'contact_phone',
            'address', 'city', 'country', 'organization_size',
            'representative_name', 'representative_email', 'representative_phone',
            'has_events_module', 'has_accommodation_module', 'has_experience_module',
            'experience_dashboard_template', 'is_student_center',
            'onboarding_completed', 'status', 'created_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at']
        extra_kwargs = {
            'logo': {'required': False, 'allow_null': True}
        }

    def to_representation(self, instance):
        """
        Normalize legacy template values to new values.
        'standard' -> 'v0'
        'free_tours' -> 'principal'
        """
        data = super().to_representation(instance)
        
        # Normalize legacy template values
        template = data.get('experience_dashboard_template')
        if template == 'standard':
            data['experience_dashboard_template'] = 'v0'
        elif template == 'free_tours':
            data['experience_dashboard_template'] = 'principal'
        
        return data


class OrganizerUserSerializer(serializers.ModelSerializer):
    """
    Serializer for organizer user model.
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = OrganizerUser
        fields = [
            'id', 'user', 'user_email', 'user_name', 'organizer',
            'is_admin', 'can_manage_events', 'can_manage_accommodations',
            'can_manage_experiences', 'can_view_reports', 'can_manage_settings',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class OrganizerSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for organizer subscription model.
    """
    plan_display = serializers.CharField(source='get_plan_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = OrganizerSubscription
        fields = [
            'id', 'organizer', 'plan', 'plan_display', 'status', 'status_display',
            'start_date', 'end_date', 'max_events', 'max_accommodations',
            'max_experiences', 'max_storage_gb', 'max_users', 'is_active',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class BillingDetailsSerializer(serializers.ModelSerializer):
    """
    Serializer for billing details.
    """
    person_type_display = serializers.CharField(source='get_person_type_display', read_only=True)
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    
    class Meta:
        model = BillingDetails
        fields = [
            'id', 'organizer', 'person_type', 'person_type_display',
            'tax_name', 'tax_id', 'billing_address',
            'document_type', 'document_type_display',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class BankingDetailsSerializer(serializers.ModelSerializer):
    """
    Serializer for banking details.
    """
    class Meta:
        model = BankingDetails
        fields = [
            'id', 'organizer', 'bank_name', 'account_type',
            'account_number', 'account_holder',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class OrganizerOnboardingSerializer(serializers.ModelSerializer):
    """
    Serializer for organizer onboarding.
    """
    has_experience_display = serializers.CharField(source='get_has_experience_display', read_only=True)
    experience_years_display = serializers.CharField(source='get_experience_years_display', read_only=True)
    event_size_display = serializers.CharField(source='get_event_size_display', read_only=True)
    experience_type_display = serializers.CharField(source='get_experience_type_display', read_only=True)
    experience_frequency_display = serializers.CharField(source='get_experience_frequency_display', read_only=True)
    accommodation_type_display = serializers.CharField(source='get_accommodation_type_display', read_only=True)
    accommodation_capacity_display = serializers.CharField(source='get_accommodation_capacity_display', read_only=True)
    
    class Meta:
        model = OrganizerOnboarding
        fields = [
            'id', 'organizer', 'selected_types',
            'organization_name', 'organization_slug', 'organization_size',
            'contact_name', 'contact_email', 'contact_phone',
            'has_experience', 'has_experience_display',
            'experience_years', 'experience_years_display',
            'event_size', 'event_size_display',
            'experience_type', 'experience_type_display',
            'experience_frequency', 'experience_frequency_display',
            'accommodation_type', 'accommodation_type_display',
            'accommodation_capacity', 'accommodation_capacity_display',
            'completed_step', 'is_completed',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate_selected_types(self, value):
        """Validate the selected_types field."""
        valid_types = ['events', 'experiences', 'accommodations']
        if not isinstance(value, list):
            raise serializers.ValidationError("Selected types must be a list")
        for type_value in value:
            if type_value not in valid_types:
                raise serializers.ValidationError(f"Invalid type: {type_value}")
        return value


class OrganizerDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed organizer information.
    """
    users = OrganizerUserSerializer(source='organizer_users', many=True, read_only=True)
    subscriptions = OrganizerSubscriptionSerializer(many=True, read_only=True)
    active_subscription = serializers.SerializerMethodField()
    onboarding_data = serializers.SerializerMethodField()
    billing_details = BillingDetailsSerializer(read_only=True)
    banking_details = BankingDetailsSerializer(read_only=True)
    has_billing_details = serializers.SerializerMethodField()
    has_banking_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Organizer
        fields = [
            'id', 'name', 'slug', 'description', 'logo',
            'website', 'contact_email', 'contact_phone',
            'address', 'city', 'country', 'organization_size',
            'representative_name', 'representative_email', 'representative_phone',
            'has_events_module', 'has_accommodation_module', 'has_experience_module',
            'onboarding_completed', 'status',
            'created_at', 'users', 'subscriptions', 'active_subscription',
            'onboarding_data', 'billing_details', 'banking_details',
            'has_billing_details', 'has_banking_details'
        ]
        read_only_fields = ['id', 'slug', 'created_at']
    
    def get_active_subscription(self, obj):
        """Get the active subscription for the organizer."""
        active_sub = obj.subscriptions.filter(status__in=['active', 'trial']).first()
        if active_sub:
            return OrganizerSubscriptionSerializer(active_sub).data
        return None
    
    def get_onboarding_data(self, obj):
        """Get the onboarding data for the organizer."""
        try:
            onboarding = obj.onboarding
            return OrganizerOnboardingSerializer(onboarding).data
        except OrganizerOnboarding.DoesNotExist:
            return None
    
    def get_has_billing_details(self, obj):
        """Check if the organizer has billing details."""
        return hasattr(obj, 'billing_details')
    
    def get_has_banking_details(self, obj):
        """Check if the organizer has banking details."""
        return hasattr(obj, 'banking_details') 