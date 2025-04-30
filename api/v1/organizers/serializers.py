"""Serializers for organizers API."""

from rest_framework import serializers

from apps.organizers.models import (
    Organizer,
    OrganizerUser,
    OrganizerSubscription,
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
            'address', 'city', 'country',
            'has_events_module', 'has_accommodation_module', 'has_experience_module',
            'created_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at']


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


class OrganizerDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed organizer information.
    """
    users = OrganizerUserSerializer(source='organizer_users', many=True, read_only=True)
    subscriptions = OrganizerSubscriptionSerializer(many=True, read_only=True)
    active_subscription = serializers.SerializerMethodField()
    
    class Meta:
        model = Organizer
        fields = [
            'id', 'name', 'slug', 'description', 'logo',
            'website', 'contact_email', 'contact_phone',
            'address', 'city', 'country',
            'has_events_module', 'has_accommodation_module', 'has_experience_module',
            'created_at', 'users', 'subscriptions', 'active_subscription'
        ]
        read_only_fields = ['id', 'slug', 'created_at']
    
    def get_active_subscription(self, obj):
        """Get the active subscription for the organizer."""
        active_sub = obj.subscriptions.filter(status__in=['active', 'trial']).first()
        if active_sub:
            return OrganizerSubscriptionSerializer(active_sub).data
        return None 