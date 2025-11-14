"""
🚀 ENTERPRISE VALIDATION MODELS
Modelos para el sistema de validación enterprise
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from apps.events.models import Event, Ticket
from apps.organizers.models import Organizer
from core.models import BaseModel

User = get_user_model()


class ValidatorSession(BaseModel):
    """
    🚀 ENTERPRISE: Sesiones de validador para tracking completo
    Cada vez que un validador inicia trabajo, se crea una sesión
    """
    validator_name = models.CharField(
        max_length=100, 
        help_text="Nombre del validador asignado"
    )
    organizer = models.ForeignKey(
        Organizer, 
        on_delete=models.CASCADE,
        related_name='validator_sessions'
    )
    event = models.ForeignKey(
        Event, 
        on_delete=models.CASCADE,
        related_name='validator_sessions'
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        help_text="Usuario que inició la sesión",
        related_name='validator_sessions'
    )
    
    # Tiempos de sesión
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Información técnica
    device_info = models.JSONField(
        default=dict, 
        help_text="Información del dispositivo (browser, OS, etc.)"
    )
    location = models.JSONField(
        default=dict, 
        help_text="Ubicación GPS si está disponible"
    )
    
    # Métricas de rendimiento
    total_scans = models.IntegerField(default=0)
    successful_validations = models.IntegerField(default=0)
    failed_validations = models.IntegerField(default=0)
    tickets_checked_in = models.IntegerField(default=0)
    
    # Métricas de tiempo
    average_scan_time_ms = models.FloatField(default=0.0)
    total_validation_time_ms = models.BigIntegerField(default=0)
    
    class Meta:
        verbose_name = "Sesión de Validador"
        verbose_name_plural = "Sesiones de Validadores"
        ordering = ['-start_time']
    
    def __str__(self):
        return f"{self.validator_name} - {self.event.title} ({self.start_time.strftime('%d/%m/%Y %H:%M')})"
    
    @property
    def duration(self):
        """Duración de la sesión"""
        if self.end_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def success_rate(self):
        """Tasa de éxito de validaciones"""
        if self.total_scans == 0:
            return 0
        return (self.successful_validations / self.total_scans) * 100
    
    @property
    def throughput_per_hour(self):
        """Tickets procesados por hora"""
        duration = self.duration
        if not duration or duration.total_seconds() == 0:
            return 0
        hours = duration.total_seconds() / 3600
        return self.total_scans / hours


class TicketValidationLog(BaseModel):
    """
    🚀 ENTERPRISE: Log completo de todas las validaciones
    Auditoría completa de cada acción realizada
    """
    ACTION_CHOICES = [
        ('scan', 'Escaneo QR'),
        ('validate', 'Validación'),
        ('check_in', 'Check-in'),
        ('status_change', 'Cambio de Estado'),
        ('note_added', 'Nota Agregada'),
        ('manual_override', 'Override Manual'),
    ]
    
    STATUS_CHOICES = [
        ('success', 'Exitoso'),
        ('error', 'Error'),
        ('warning', 'Advertencia'),
        ('info', 'Información'),
    ]
    
    # Relaciones principales
    ticket = models.ForeignKey(
        Ticket, 
        on_delete=models.CASCADE, 
        related_name='validation_logs',
        null=True,  # Puede ser null si el ticket no se encontró
        blank=True
    )
    validator_session = models.ForeignKey(
        ValidatorSession, 
        on_delete=models.CASCADE,
        related_name='validation_logs'
    )
    
    # Información de la acción
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    message = models.TextField(help_text="Descripción detallada de la acción")
    
    # Datos técnicos
    scan_time_ms = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Tiempo de escaneo en milisegundos"
    )
    qr_data = models.TextField(
        blank=True, 
        help_text="Datos completos del QR escaneado"
    )
    device_location = models.JSONField(
        default=dict, 
        help_text="Ubicación GPS del dispositivo al momento de la acción"
    )
    
    # Metadatos adicionales
    metadata = models.JSONField(
        default=dict, 
        help_text="Datos adicionales específicos de la acción"
    )
    
    # Información de errores
    error_code = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Código de error específico"
    )
    error_details = models.JSONField(
        default=dict,
        help_text="Detalles técnicos del error"
    )
    
    class Meta:
        verbose_name = "Log de Validación"
        verbose_name_plural = "Logs de Validación"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['validator_session', '-created_at']),
            models.Index(fields=['ticket', '-created_at']),
            models.Index(fields=['action', 'status']),
        ]
    
    def __str__(self):
        ticket_info = f"Ticket {self.ticket.ticket_number}" if self.ticket else "Sin ticket"
        return f"{self.get_action_display()} - {ticket_info} ({self.created_at.strftime('%H:%M:%S')})"


class TicketNote(BaseModel):
    """
    🚀 ENTERPRISE: Notas de validadores en tickets
    Sistema de notas para tracking de incidencias
    """
    NOTE_TYPES = [
        ('general', 'Nota General'),
        ('check_in', 'Nota de Check-in'),
        ('issue', 'Incidencia'),
        ('resolution', 'Resolución'),
        ('security', 'Seguridad'),
        ('vip', 'VIP/Especial'),
    ]
    
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='validation_notes'  # Cambiar para evitar conflicto
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        help_text="Usuario que creó la nota",
        related_name='validation_notes_created'
    )
    validator_session = models.ForeignKey(
        ValidatorSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Sesión de validador cuando se creó la nota"
    )
    
    note_type = models.CharField(
        max_length=20,
        choices=NOTE_TYPES,
        default='general'
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Título opcional para la nota"
    )
    content = models.TextField(help_text="Contenido de la nota")
    
    # Flags de importancia
    is_important = models.BooleanField(
        default=False,
        help_text="Marcar como importante"
    )
    is_resolved = models.BooleanField(
        default=False,
        help_text="Marcar como resuelto"
    )
    
    # Información adicional
    attachments = models.JSONField(
        default=list,
        help_text="URLs de archivos adjuntos"
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Metadatos adicionales"
    )
    
    class Meta:
        verbose_name = "Nota de Ticket"
        verbose_name_plural = "Notas de Tickets"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Nota en {self.ticket.ticket_number} por {self.user.get_full_name() or self.user.username}"


class EventValidationStats(BaseModel):
    """
    🚀 ENTERPRISE: Estadísticas de validación por evento
    Cache de estadísticas para dashboards en tiempo real
    """
    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name='validation_stats'
    )
    
    # Contadores generales
    total_tickets = models.IntegerField(default=0)
    tickets_scanned = models.IntegerField(default=0)
    tickets_validated = models.IntegerField(default=0)
    tickets_checked_in = models.IntegerField(default=0)
    tickets_rejected = models.IntegerField(default=0)
    
    # Métricas de tiempo
    first_scan_time = models.DateTimeField(null=True, blank=True)
    last_scan_time = models.DateTimeField(null=True, blank=True)
    average_scan_time_ms = models.FloatField(default=0.0)
    peak_throughput_per_minute = models.IntegerField(default=0)
    
    # Estadísticas de validadores
    active_validators = models.IntegerField(default=0)
    total_validator_sessions = models.IntegerField(default=0)
    
    # Última actualización
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Estadísticas de Validación"
        verbose_name_plural = "Estadísticas de Validación"
    
    def __str__(self):
        return f"Stats {self.event.title}"
    
    @property
    def scan_rate(self):
        """Porcentaje de tickets escaneados"""
        if self.total_tickets == 0:
            return 0
        return (self.tickets_scanned / self.total_tickets) * 100
    
    @property
    def validation_success_rate(self):
        """Tasa de éxito de validaciones"""
        if self.tickets_scanned == 0:
            return 0
        return (self.tickets_validated / self.tickets_scanned) * 100
    
    @property
    def checkin_rate(self):
        """Porcentaje de check-ins completados"""
        if self.total_tickets == 0:
            return 0
        return (self.tickets_checked_in / self.total_tickets) * 100
