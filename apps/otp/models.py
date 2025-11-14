from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import RegexValidator
import secrets
import string
from datetime import timedelta

User = get_user_model()


class OTPPurpose(models.TextChoices):
    """Diferentes propósitos para los códigos OTP"""
    EVENT_CREATION = 'event_creation', 'Creación de Evento'
    LOGIN = 'login', 'Inicio de Sesión'
    TICKET_ACCESS = 'ticket_access', 'Acceso a Tickets'
    PASSWORD_RESET = 'password_reset', 'Recuperación de Contraseña'
    EMAIL_VERIFICATION = 'email_verification', 'Verificación de Email'
    ACCOUNT_CREATION = 'account_creation', 'Creación de Cuenta'


class OTPManager(models.Manager):
    def generate_code(self, email, purpose, expiry_minutes=10, user=None, metadata=None):
        """
        Genera un nuevo código OTP para un email y propósito específico
        """
        # Invalidar códigos anteriores para el mismo email y propósito
        self.filter(
            email__iexact=email,
            purpose=purpose,
            is_used=False,
            expires_at__gt=timezone.now()
        ).update(is_used=True, used_at=timezone.now())
        
        # Generar código de 6 dígitos
        code = ''.join(secrets.choice(string.digits) for _ in range(6))
        
        # Crear nuevo OTP
        otp = self.create(
            email=email.lower(),
            code=code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=expiry_minutes),
            user=user,
            metadata=metadata or {}
        )
        
        return otp
    
    def validate_code(self, email, code, purpose):
        """
        Valida un código OTP
        Returns: (is_valid, otp_instance, error_message)
        """
        try:
            otp = self.get(
                email__iexact=email,
                code=code,
                purpose=purpose,
                is_used=False,
                expires_at__gt=timezone.now()
            )
            
            # Marcar como usado
            otp.is_used = True
            otp.used_at = timezone.now()
            otp.save(update_fields=['is_used', 'used_at'])
            
            return True, otp, None
            
        except self.model.DoesNotExist:
            # Verificar si existe pero está expirado o usado
            expired_or_used = self.filter(
                email__iexact=email,
                code=code,
                purpose=purpose
            ).first()
            
            if expired_or_used:
                if expired_or_used.is_used:
                    return False, None, "Código ya utilizado"
                elif expired_or_used.expires_at <= timezone.now():
                    return False, None, "Código expirado"
            
            return False, None, "Código inválido"
    
    def cleanup_expired(self):
        """Limpia códigos expirados (tarea programada)"""
        expired_count = self.filter(
            expires_at__lt=timezone.now()
        ).delete()[0]
        return expired_count
    
    def get_active_for_email(self, email, purpose):
        """Obtiene código activo para un email y propósito"""
        return self.filter(
            email__iexact=email,
            purpose=purpose,
            is_used=False,
            expires_at__gt=timezone.now()
        ).first()


class OTP(models.Model):
    """
    Modelo para códigos OTP (One-Time Password)
    Sistema multifuncional para diferentes tipos de autenticación
    """
    
    email = models.EmailField(
        verbose_name="Email",
        help_text="Email al que se envía el código"
    )
    
    code = models.CharField(
        max_length=6,
        validators=[RegexValidator(r'^\d{6}$', 'El código debe tener 6 dígitos')],
        verbose_name="Código OTP"
    )
    
    purpose = models.CharField(
        max_length=20,
        choices=OTPPurpose.choices,
        verbose_name="Propósito",
        help_text="Para qué se usa este código"
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Usuario",
        help_text="Usuario asociado (si existe)"
    )
    
    # Campos de seguridad y control
    is_used = models.BooleanField(
        default=False,
        verbose_name="¿Usado?",
        help_text="Si el código ya fue utilizado"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Creado"
    )
    
    expires_at = models.DateTimeField(
        verbose_name="Expira",
        help_text="Cuándo expira el código"
    )
    
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Usado en",
        help_text="Cuándo se usó el código"
    )
    
    # Campos para tracking y seguridad
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP de creación"
    )
    
    user_agent = models.TextField(
        null=True,
        blank=True,
        verbose_name="User Agent"
    )
    
    attempts = models.PositiveIntegerField(
        default=0,
        verbose_name="Intentos",
        help_text="Número de intentos de validación"
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadatos",
        help_text="Información adicional contextual"
    )
    
    objects = OTPManager()
    
    class Meta:
        verbose_name = "Código OTP"
        verbose_name_plural = "Códigos OTP"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'purpose', 'is_used']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"OTP {self.code} - {self.email} ({self.get_purpose_display()})"
    
    @property
    def is_expired(self):
        """Verifica si el código ha expirado"""
        return timezone.now() > self.expires_at
    
    @property
    def is_valid(self):
        """Verifica si el código es válido (no usado y no expirado)"""
        return not self.is_used and not self.is_expired
    
    @property
    def time_remaining(self):
        """Tiempo restante para expiración"""
        if self.is_expired:
            return timedelta(0)
        return self.expires_at - timezone.now()
    
    def increment_attempts(self):
        """Incrementa el contador de intentos"""
        self.attempts += 1
        self.save(update_fields=['attempts'])
    
    def invalidate(self):
        """Invalida el código marcándolo como usado"""
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=['is_used', 'used_at'])


class OTPAttempt(models.Model):
    """
    Registro de intentos de validación para seguridad
    """
    otp = models.ForeignKey(
        OTP,
        on_delete=models.CASCADE,
        related_name='validation_attempts'
    )
    
    attempted_code = models.CharField(
        max_length=6,
        verbose_name="Código intentado"
    )
    
    is_successful = models.BooleanField(
        default=False,
        verbose_name="¿Exitoso?"
    )
    
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP del intento"
    )
    
    user_agent = models.TextField(
        null=True,
        blank=True,
        verbose_name="User Agent del intento"
    )
    
    attempted_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Intentado en"
    )
    
    class Meta:
        verbose_name = "Intento de OTP"
        verbose_name_plural = "Intentos de OTP"
        ordering = ['-attempted_at']
