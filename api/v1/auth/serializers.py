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
    is_erasmus = serializers.SerializerMethodField()
    locale = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, min_length=6)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'full_name', 'is_organizer', 'is_validator',
            'is_guest', 'is_erasmus', 'locale', 'is_superuser', 'is_staff', 'is_profile_complete', 'has_password',
            'date_joined', 'last_login', 'profile_completed_at', 'password'
        ]
        read_only_fields = [
            'id', 'email', 'username', 'date_joined', 'last_login',
            'is_organizer', 'is_validator', 'is_guest', 'is_erasmus', 'locale', 'is_superuser', 'is_staff', 'profile_completed_at'
        ]

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_is_erasmus(self, obj):
        """True if user has at least one linked Erasmus lead (secciones adicionales en perfil)."""
        if getattr(obj, '_is_erasmus', None) is not None:
            return obj._is_erasmus
        return obj.erasmus_leads.exists()

    def get_locale(self, obj):
        """Preferred UI locale. From Erasmus lead form_locale if user is Erasmus; otherwise default 'es'."""
        if getattr(obj, '_locale', None) is not None:
            return obj._locale
        lead = obj.erasmus_leads.order_by('-created_at').first()
        if lead and getattr(lead, 'form_locale', None):
            loc = (lead.form_locale or '').strip().lower()
            if loc in ('es', 'en', 'pt', 'de', 'it', 'fr'):
                return loc
        return 'es'

    def update(self, instance, validated_data):
        """Actualizar perfil del usuario"""
        # Si se proporciona una contraseña, hashearla y persistirla de inmediato.
        # (Si no se guarda aquí, al llamar mark_profile_complete() o save(update_fields=...)
        # la contraseña no se incluye y nunca se persiste → login falla.)
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
            instance.last_password_change = timezone.now()
            instance.save(update_fields=['password', 'last_password_change'])

        # Actualizar otros campos en memoria
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # 🚀 ENTERPRISE: Marcar perfil como completo si se proporcionaron first_name y last_name
        set_profile_completed = False
        if validated_data.get('first_name') and validated_data.get('last_name'):
            if instance.is_guest:
                instance.mark_profile_complete()
            elif not instance.profile_completed_at:
                instance.profile_completed_at = timezone.now()
                set_profile_completed = True

        # Persistir todos los campos actualizados (evita perder phone_number u otros al usar update_fields parcial)
        update_fields = list(validated_data.keys())
        if set_profile_completed:
            update_fields.append('profile_completed_at')
        if update_fields:
            instance.save(update_fields=update_fields)

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


class OrganizerOTPSerializer(serializers.Serializer):
    """Serializer para OTP de organizadores"""
    email = serializers.EmailField()
    
    def validate_email(self, value):
        return value.lower().strip()


class OrganizerOTPValidateSerializer(serializers.Serializer):
    """Serializer para validar OTP de organizadores"""
    email = serializers.EmailField()
    code = serializers.CharField(min_length=6, max_length=6)
    
    def validate_email(self, value):
        return value.lower().strip()
    
    def validate_code(self, value):
        code = value.strip().replace(' ', '')
        if not code.isdigit():
            raise serializers.ValidationError("El código debe contener solo números")
        return code


class OrganizerProfileSetupSerializer(serializers.Serializer):
    """Serializer para configuración inicial del perfil de organizador"""
    organization_name = serializers.CharField(max_length=255, required=False)
    contact_name = serializers.CharField(max_length=255, required=False)
    contact_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, min_length=6)
    password_confirm = serializers.CharField(write_only=True, required=False)
    
    def validate_organization_name(self, value):
        """Validar que el nombre no empiece con 'Organizador ' (nombre genérico)"""
        if value and value.strip().startswith('Organizador '):
            raise serializers.ValidationError(
                "El nombre de la organización no puede empezar con 'Organizador '. "
                "Por favor, ingresa un nombre personalizado para tu organización."
            )
        return value.strip() if value else value
    
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


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer para cambio de contraseña con contraseña actual"""
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=6)
    new_password_confirm = serializers.CharField(write_only=True, required=False)
    
    def validate_new_password(self, value):
        """Validar contraseña nueva con validadores de Django"""
        validate_password(value)
        return value
    
    def validate(self, attrs):
        """Validar que las contraseñas coincidan si se proporciona confirmación"""
        new_password = attrs.get('new_password')
        new_password_confirm = attrs.get('new_password_confirm')
        
        # Si se proporciona confirmación, validar que coincidan
        if new_password_confirm and new_password != new_password_confirm:
            raise serializers.ValidationError({
                'new_password_confirm': 'Las contraseñas no coinciden'
            })
        
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer para solicitar restablecimiento de contraseña vía OTP"""
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        return value.lower().strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer para restablecer contraseña con código OTP"""
    email = serializers.EmailField(required=True)
    code = serializers.CharField(min_length=6, max_length=6, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=6)
    new_password_confirm = serializers.CharField(write_only=True, required=False)
    
    def validate_email(self, value):
        return value.lower().strip()
    
    def validate_code(self, value):
        """Validar formato del código OTP"""
        code = value.strip().replace(' ', '')
        if not code.isdigit():
            raise serializers.ValidationError("El código debe contener solo números")
        return code
    
    def validate_new_password(self, value):
        """Validar contraseña nueva con validadores de Django"""
        validate_password(value)
        return value
    
    def validate(self, attrs):
        """Validar que las contraseñas coincidan si se proporciona confirmación"""
        new_password = attrs.get('new_password')
        new_password_confirm = attrs.get('new_password_confirm')
        
        if new_password_confirm and new_password != new_password_confirm:
            raise serializers.ValidationError({
                'new_password_confirm': 'Las contraseñas no coinciden'
            })
        
        return attrs