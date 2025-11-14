from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import OTP, OTPPurpose

User = get_user_model()


class OTPGenerateSerializer(serializers.Serializer):
    """Serializer para generar códigos OTP"""
    
    email = serializers.EmailField(
        help_text="Email al que enviar el código"
    )
    
    purpose = serializers.ChoiceField(
        choices=OTPPurpose.choices,
        help_text="Propósito del código OTP"
    )
    
    metadata = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Metadatos adicionales (opcional)"
    )
    
    def validate_email(self, value):
        """Validación del email"""
        return value.lower().strip()


class OTPValidateSerializer(serializers.Serializer):
    """Serializer para validar códigos OTP"""
    
    email = serializers.EmailField(
        help_text="Email del usuario"
    )
    
    code = serializers.CharField(
        min_length=6,
        max_length=6,
        help_text="Código OTP de 6 dígitos"
    )
    
    purpose = serializers.ChoiceField(
        choices=OTPPurpose.choices,
        help_text="Propósito del código OTP"
    )
    
    def validate_email(self, value):
        """Validación del email"""
        return value.lower().strip()
    
    def validate_code(self, value):
        """Validación del código"""
        # Remover espacios y verificar que sea numérico
        code = value.strip().replace(' ', '')
        if not code.isdigit():
            raise serializers.ValidationError("El código debe contener solo números")
        if len(code) != 6:
            raise serializers.ValidationError("El código debe tener exactamente 6 dígitos")
        return code


class OTPResendSerializer(serializers.Serializer):
    """Serializer para reenviar códigos OTP"""
    
    email = serializers.EmailField(
        help_text="Email al que reenviar el código"
    )
    
    purpose = serializers.ChoiceField(
        choices=OTPPurpose.choices,
        help_text="Propósito del código OTP"
    )
    
    def validate_email(self, value):
        """Validación del email"""
        return value.lower().strip()


class OTPStatusSerializer(serializers.Serializer):
    """Serializer para consultar el estado de un OTP"""
    
    email = serializers.EmailField(
        help_text="Email del usuario"
    )
    
    purpose = serializers.ChoiceField(
        choices=OTPPurpose.choices,
        help_text="Propósito del código OTP"
    )
    
    def validate_email(self, value):
        """Validación del email"""
        return value.lower().strip()


class OTPResponseSerializer(serializers.Serializer):
    """Serializer para respuestas de OTP"""
    
    success = serializers.BooleanField()
    message = serializers.CharField()
    expires_at = serializers.DateTimeField(required=False)
    time_remaining_minutes = serializers.IntegerField(required=False)
    attempts = serializers.IntegerField(required=False)
    max_attempts = serializers.IntegerField(required=False)


class OTPValidationResponseSerializer(serializers.Serializer):
    """Serializer para respuestas de validación de OTP"""
    
    success = serializers.BooleanField()
    message = serializers.CharField()
    user_id = serializers.IntegerField(required=False, allow_null=True)
    user_email = serializers.EmailField(required=False, allow_null=True)
    is_new_user = serializers.BooleanField(required=False)
    
    # Datos adicionales según el propósito
    next_step = serializers.CharField(required=False)
    requires_onboarding = serializers.BooleanField(required=False)
    access_token = serializers.CharField(required=False)


class EventCreationOTPSerializer(serializers.Serializer):
    """Serializer específico para OTP de creación de eventos"""
    
    email = serializers.EmailField()
    event_title = serializers.CharField(max_length=200, required=False)
    event_type = serializers.CharField(max_length=50, required=False)
    is_paid_event = serializers.BooleanField(default=False)
    
    def validate_email(self, value):
        return value.lower().strip()


class LoginOTPSerializer(serializers.Serializer):
    """Serializer específico para OTP de login"""
    
    email = serializers.EmailField()
    remember_me = serializers.BooleanField(default=False)
    
    def validate_email(self, value):
        return value.lower().strip()


class TicketAccessOTPSerializer(serializers.Serializer):
    """Serializer específico para OTP de acceso a tickets"""
    
    email = serializers.EmailField()
    order_id = serializers.CharField(max_length=100, required=False)
    event_id = serializers.CharField(max_length=100, required=False)
    
    def validate_email(self, value):
        return value.lower().strip()


class OTPInfoSerializer(serializers.ModelSerializer):
    """Serializer para información básica de OTP (sin revelar el código)"""
    
    purpose_display = serializers.CharField(source='get_purpose_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    time_remaining_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = OTP
        fields = [
            'email', 'purpose', 'purpose_display', 'created_at', 
            'expires_at', 'is_used', 'is_expired', 'is_valid',
            'attempts', 'time_remaining_minutes'
        ]
    
    def get_time_remaining_minutes(self, obj):
        """Calcula los minutos restantes"""
        if obj.is_expired or obj.is_used:
            return 0
        return max(0, int(obj.time_remaining.total_seconds() // 60))
