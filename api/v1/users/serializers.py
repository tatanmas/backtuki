"""Serializers for users API."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.models import Profile

User = get_user_model()


class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for profile model.
    """
    class Meta:
        model = Profile
        fields = [
            'address', 'city', 'country', 'bio', 'birth_date'
        ]


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for basic user information.
    """
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'is_active', 'date_joined', 'is_organizer', 'is_validator',
            'last_password_change'
        ]
        read_only_fields = ['id', 'date_joined', 'last_password_change']


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed user information.
    """
    profile = ProfileSerializer()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'profile_picture', 'is_active', 'date_joined',
            'last_login', 'is_organizer', 'is_validator', 'profile'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']
    
    def update(self, instance, validated_data):
        """
        Update user and profile.
        """
        profile_data = validated_data.pop('profile', None)
        
        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update profile if data exists
        if profile_data:
            profile = instance.profile
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()
        
        return instance 