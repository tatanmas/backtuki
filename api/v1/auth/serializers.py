"""Serializers for authentication API."""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.utils.translation import gettext_lazy as _
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import serializers

from apps.users.models import Profile

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'password', 'password_confirm',
            'first_name', 'last_name', 'phone_number'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        """
        Check that the passwords match.
        """
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError(
                {'password_confirm': _("Passwords don't match.")}
            )
        return data
    
    def create(self, validated_data):
        """
        Create and return a new user instance.
        """
        # Remove password_confirm field
        validated_data.pop('password_confirm')
        
        # Create the user
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone_number=validated_data.get('phone_number', None)
        )
        
        return user


class PasswordResetSerializer(serializers.Serializer):
    """
    Serializer for requesting a password reset.
    """
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        """
        Validate that the email exists.
        """
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                _("User with this email address does not exist.")
            )
        return value
    
    def save(self):
        """
        Generate a password reset token and send the email.
        """
        email = self.validated_data['email']
        user = User.objects.get(email=email)
        
        # Generate token
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Build reset url (frontend url)
        reset_url = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"
        
        # Send email
        send_mail(
            subject=_("Reset your Tuki password"),
            message=_(
                f"Follow this link to reset your password: {reset_url}\n\n"
                f"If you didn't request this, please ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False
        )


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for confirming a password reset.
    """
    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    
    def validate(self, data):
        """
        Validate token and passwords.
        """
        try:
            uid = force_str(urlsafe_base64_decode(data['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError(
                {'uid': _("Invalid user ID.")}
            )
        
        if not default_token_generator.check_token(user, data['token']):
            raise serializers.ValidationError(
                {'token': _("Invalid or expired token.")}
            )
        
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError(
                {'password_confirm': _("Passwords don't match.")}
            )
        
        self.user = user
        return data
    
    def save(self):
        """
        Set the new password.
        """
        self.user.set_password(self.validated_data['password'])
        self.user.save()


class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile.
    """
    class Meta:
        model = Profile
        fields = [
            'address', 'city', 'country', 'bio', 'birth_date'
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for retrieving and updating user profile.
    """
    profile = ProfileSerializer()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'profile_picture', 'profile'
        ]
        read_only_fields = ['id', 'email']
    
    def update(self, instance, validated_data):
        """
        Update user and profile.
        """
        profile_data = validated_data.pop('profile', {})
        
        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update profile fields
        profile = instance.profile
        for attr, value in profile_data.items():
            setattr(profile, attr, value)
        profile.save()
        
        return instance 