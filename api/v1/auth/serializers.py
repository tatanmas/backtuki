from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from core.utils import generate_username

User = get_user_model()


class UserCheckSerializer(serializers.Serializer):
    """Serializer para verificar si un usuario existe"""
    email = serializers.EmailField()
    
    def validate_email(self, value):
        return value.lower().strip()


class UserLoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate_email(self, value):
        return value.lower()


class OTPLoginSerializer(serializers.Serializer):
    """Serializer para login con OTP"""
    email = serializers.EmailField()
    code = serializers.CharField(min_length=6, max_length=6)
    
    def validate_email(self, value):
        return value.lower().strip()
    
    def validate_code(self, value):
        code = value.strip().replace(' ', '')
        if not code.isdigit():
            raise serializers.ValidationError("El código debe contener solo números")
        return code


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile."""
    
    full_name = serializers.SerializerMethodField()
    is_profile_complete = serializers.ReadOnlyField()
    has_password = serializers.ReadOnlyField()
    password = serializers.CharField(write_only=True, required=False, min_length=6)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'full_name', 'is_organizer', 'is_validator',
            'is_guest', 'is_profile_complete', 'has_password',
            'date_joined', 'last_login', 'profile_completed_at', 'password'
        ]
        read_only_fields = [
            'id', 'email', 'username', 'date_joined', 'last_login',
            'is_organizer', 'is_validator', 'is_guest', 'profile_completed_at'
        ]
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    
    def update(self, instance, validated_data):
        """Actualizar perfil del usuario"""
        # Si se proporciona una contraseña, hashearla
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
            instance.last_password_change = timezone.now()
        
        # Actualizar otros campos
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration via OTP."""
    
    password = serializers.CharField(
        write_only=True,
        min_length=6,
        required=False
    )
    password_confirm = serializers.CharField(write_only=True, required=False)
    code = serializers.CharField(min_length=6, max_length=6, write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone_number', 'password', 'password_confirm', 'code']
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
        }
    
    def validate(self, attrs):
        """Validate passwords if provided."""
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')
        
        if password and password_confirm:
            if password != password_confirm:
                raise serializers.ValidationError("Las contraseñas no coinciden")
        elif password and not password_confirm:
            raise serializers.ValidationError("Confirma tu contraseña")
        
        return attrs
    
    def validate_email(self, value):
        """Validate email format."""
        return value.lower().strip()
    
    def validate_code(self, value):
        """Validate OTP code format."""
        code = value.strip().replace(' ', '')
        if not code.isdigit():
            raise serializers.ValidationError("El código debe contener solo números")
        return code


class GuestUserSerializer(serializers.Serializer):
    """Serializer para crear usuario guest desde compra"""
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    order_id = serializers.CharField(max_length=100, required=False)
    
    def validate_email(self, value):
        return value.lower().strip()