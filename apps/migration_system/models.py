"""
🚀 ENTERPRISE MIGRATION SYSTEM - Models

Modelos para tracking de migraciones, logs y checkpoints.
"""

import uuid
import json
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.models import TimeStampedModel

User = get_user_model()


class MigrationJob(TimeStampedModel):
    """
    Job de migración que trackea el estado y progreso de una migración en curso.
    """
    
    STATUS_CHOICES = (
        ('pending', _('Pending')),
        ('in_progress', _('In Progress')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('cancelled', _('Cancelled')),
        ('rolling_back', _('Rolling Back')),
        ('rolled_back', _('Rolled Back')),
    )
    
    DIRECTION_CHOICES = (
        ('export', _('Export')),
        ('import', _('Import')),
        ('push', _('Push to Target')),
        ('pull', _('Pull from Source')),
    )
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    direction = models.CharField(
        _("direction"),
        max_length=20,
        choices=DIRECTION_CHOICES
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # URLs de origen/destino para push/pull
    source_url = models.URLField(
        _("source URL"),
        blank=True,
        null=True,
        help_text=_("URL del backend origen (para pull)")
    )
    target_url = models.URLField(
        _("target URL"),
        blank=True,
        null=True,
        help_text=_("URL del backend destino (para push)")
    )
    
    # Token de autenticación (encriptado)
    auth_token_hash = models.CharField(
        _("auth token hash"),
        max_length=255,
        blank=True,
        help_text=_("Hash del token de autenticación")
    )
    
    # Progreso
    progress_percent = models.IntegerField(
        _("progress percentage"),
        default=0,
        help_text=_("Porcentaje de progreso (0-100)")
    )
    current_step = models.CharField(
        _("current step"),
        max_length=255,
        blank=True,
        help_text=_("Descripción del paso actual")
    )
    
    # Archivo de export generado (si aplica)
    export_file_path = models.CharField(
        _("export file path"),
        max_length=500,
        blank=True,
        null=True
    )
    export_file_size_mb = models.DecimalField(
        _("export file size (MB)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Estadísticas
    total_models = models.IntegerField(
        _("total models"),
        default=0
    )
    models_completed = models.IntegerField(
        _("models completed"),
        default=0
    )
    total_records = models.IntegerField(
        _("total records"),
        default=0
    )
    records_processed = models.IntegerField(
        _("records processed"),
        default=0
    )
    total_files = models.IntegerField(
        _("total files"),
        default=0
    )
    files_transferred = models.IntegerField(
        _("files transferred"),
        default=0
    )
    
    # Tiempos
    started_at = models.DateTimeField(
        _("started at"),
        null=True,
        blank=True
    )
    completed_at = models.DateTimeField(
        _("completed at"),
        null=True,
        blank=True
    )
    duration_seconds = models.IntegerField(
        _("duration (seconds)"),
        null=True,
        blank=True
    )
    
    # Errores
    error_message = models.TextField(
        _("error message"),
        blank=True,
        help_text=_("Mensaje de error si la migración falló")
    )
    error_traceback = models.TextField(
        _("error traceback"),
        blank=True,
        help_text=_("Traceback completo del error")
    )
    
    # Configuración
    config = models.JSONField(
        _("configuration"),
        default=dict,
        blank=True,
        help_text=_("Configuración usada para esta migración")
    )
    
    # Usuario que ejecutó la migración
    executed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='migration_jobs',
        verbose_name=_("executed by")
    )
    
    # Checkpoint asociado
    checkpoint = models.ForeignKey(
        'MigrationCheckpoint',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='migration_jobs',
        verbose_name=_("checkpoint")
    )
    
    class Meta:
        verbose_name = _("migration job")
        verbose_name_plural = _("migration jobs")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['direction', 'status']),
        ]
    
    def __str__(self):
        return f"{self.get_direction_display()} - {self.get_status_display()} ({self.progress_percent}%)"
    
    def start(self):
        """Marca el job como iniciado."""
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])
    
    def complete(self):
        """Marca el job como completado."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.progress_percent = 100
        self.save(update_fields=['status', 'completed_at', 'duration_seconds', 'progress_percent'])
    
    def fail(self, error_message, traceback=None):
        """Marca el job como fallido."""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        if traceback:
            self.error_traceback = traceback
        if self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        self.save(update_fields=['status', 'completed_at', 'error_message', 'error_traceback', 'duration_seconds'])
    
    def update_progress(self, percent, step_description=None):
        """Actualiza el progreso del job."""
        self.progress_percent = min(percent, 100)
        if step_description:
            self.current_step = step_description
        self.save(update_fields=['progress_percent', 'current_step'])


class MigrationLog(models.Model):
    """
    Log detallado de operaciones durante una migración.
    """
    
    LEVEL_CHOICES = (
        ('debug', _('Debug')),
        ('info', _('Info')),
        ('warning', _('Warning')),
        ('error', _('Error')),
        ('critical', _('Critical')),
    )
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    job = models.ForeignKey(
        MigrationJob,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name=_("migration job")
    )
    level = models.CharField(
        _("level"),
        max_length=20,
        choices=LEVEL_CHOICES,
        default='info'
    )
    message = models.TextField(
        _("message"),
        help_text=_("Mensaje del log")
    )
    
    # Contexto adicional
    model_name = models.CharField(
        _("model name"),
        max_length=100,
        blank=True,
        null=True,
        default='',
        help_text=_("Modelo afectado (ej: events.Event)")
    )
    record_count = models.IntegerField(
        _("record count"),
        null=True,
        blank=True,
        help_text=_("Cantidad de registros procesados")
    )
    duration_ms = models.IntegerField(
        _("duration (ms)"),
        null=True,
        blank=True,
        help_text=_("Duración de la operación en milisegundos")
    )
    
    # Metadata adicional
    metadata = models.JSONField(
        _("metadata"),
        default=dict,
        blank=True,
        help_text=_("Información adicional sobre la operación")
    )
    
    # Timestamp
    timestamp = models.DateTimeField(
        _("timestamp"),
        default=timezone.now,
        db_index=True
    )
    
    class Meta:
        verbose_name = _("migration log")
        verbose_name_plural = _("migration logs")
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['job', 'timestamp']),
            models.Index(fields=['job', 'level']),
        ]
    
    def __str__(self):
        return f"[{self.level.upper()}] {self.message[:50]}"


class MigrationCheckpoint(TimeStampedModel):
    """
    Checkpoint/snapshot de datos antes de una migración crítica.
    Permite rollback si algo sale mal.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("Nombre descriptivo del checkpoint")
    )
    description = models.TextField(
        _("description"),
        blank=True,
        help_text=_("Descripción de qué contiene este checkpoint")
    )
    
    # Archivo del snapshot
    snapshot_file_path = models.CharField(
        _("snapshot file path"),
        max_length=500,
        help_text=_("Ruta del archivo con el snapshot de datos")
    )
    snapshot_size_mb = models.DecimalField(
        _("snapshot size (MB)"),
        max_digits=10,
        decimal_places=2
    )
    
    # Estadísticas del checkpoint
    total_models = models.IntegerField(
        _("total models"),
        default=0
    )
    total_records = models.IntegerField(
        _("total records"),
        default=0
    )
    total_files = models.IntegerField(
        _("total files"),
        default=0
    )
    
    # Metadata
    database_version = models.CharField(
        _("database version"),
        max_length=100,
        blank=True
    )
    environment = models.CharField(
        _("environment"),
        max_length=50,
        blank=True,
        help_text=_("Entorno donde se creó (GCP, Local, etc)")
    )
    
    # Estado
    is_valid = models.BooleanField(
        _("is valid"),
        default=True,
        help_text=_("Si el checkpoint es válido y puede usarse para restore")
    )
    used_for_restore = models.BooleanField(
        _("used for restore"),
        default=False,
        help_text=_("Si este checkpoint fue usado para hacer restore")
    )
    restored_at = models.DateTimeField(
        _("restored at"),
        null=True,
        blank=True
    )
    
    # Usuario que creó el checkpoint
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='migration_checkpoints',
        verbose_name=_("created by")
    )
    
    # Expiración (opcional)
    expires_at = models.DateTimeField(
        _("expires at"),
        null=True,
        blank=True,
        help_text=_("Fecha de expiración del checkpoint")
    )
    
    class Meta:
        verbose_name = _("migration checkpoint")
        verbose_name_plural = _("migration checkpoints")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_valid', 'created_at']),
            models.Index(fields=['environment', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    @property
    def is_expired(self):
        """Verifica si el checkpoint expiró."""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at
    
    def mark_as_used(self):
        """Marca el checkpoint como usado para restore."""
        self.used_for_restore = True
        self.restored_at = timezone.now()
        self.save(update_fields=['used_for_restore', 'restored_at'])


class MigrationToken(models.Model):
    """
    Token de autenticación específico para operaciones de migración.
    Más seguro que reutilizar tokens de API normales.
    """
    
    PERMISSION_CHOICES = (
        ('read', _('Read Only')),
        ('write', _('Write Only')),
        ('read_write', _('Read and Write')),
        ('admin', _('Admin (Full Access)')),
    )
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    token = models.CharField(
        _("token"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("Token único para autenticación")
    )
    description = models.CharField(
        _("description"),
        max_length=255,
        help_text=_("Descripción del propósito del token")
    )
    permissions = models.CharField(
        _("permissions"),
        max_length=20,
        choices=PERMISSION_CHOICES,
        default='read_write'
    )
    
    # Seguridad
    allowed_ips = models.JSONField(
        _("allowed IPs"),
        default=list,
        blank=True,
        help_text=_("Lista de IPs permitidas (vacío = todas)")
    )
    allowed_domains = models.JSONField(
        _("allowed domains"),
        default=list,
        blank=True,
        help_text=_("Lista de dominios permitidos")
    )
    
    # Expiración
    expires_at = models.DateTimeField(
        _("expires at"),
        help_text=_("Fecha y hora de expiración del token")
    )
    
    # Uso único
    is_single_use = models.BooleanField(
        _("is single use"),
        default=False,
        help_text=_("Si el token solo puede usarse una vez")
    )
    used_at = models.DateTimeField(
        _("used at"),
        null=True,
        blank=True
    )
    
    # Tracking
    usage_count = models.IntegerField(
        _("usage count"),
        default=0
    )
    last_used_at = models.DateTimeField(
        _("last used at"),
        null=True,
        blank=True
    )
    last_used_ip = models.GenericIPAddressField(
        _("last used IP"),
        null=True,
        blank=True
    )
    
    # Auditoría
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='migration_tokens',
        verbose_name=_("created by")
    )
    created_at = models.DateTimeField(
        _("created at"),
        default=timezone.now
    )
    revoked_at = models.DateTimeField(
        _("revoked at"),
        null=True,
        blank=True
    )
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revoked_migration_tokens',
        verbose_name=_("revoked by")
    )
    
    class Meta:
        verbose_name = _("migration token")
        verbose_name_plural = _("migration tokens")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.description} - {self.token[:8]}..."
    
    @property
    def is_valid(self):
        """Verifica si el token es válido."""
        if self.revoked_at:
            return False
        if timezone.now() > self.expires_at:
            return False
        if self.is_single_use and self.used_at:
            return False
        return True
    
    def mark_used(self, ip_address=None):
        """Marca el token como usado."""
        self.usage_count += 1
        self.last_used_at = timezone.now()
        if ip_address:
            self.last_used_ip = ip_address
        if self.is_single_use and not self.used_at:
            self.used_at = timezone.now()
        self.save(update_fields=['usage_count', 'last_used_at', 'last_used_ip', 'used_at'])
    
    def revoke(self, user=None):
        """Revoca el token."""
        self.revoked_at = timezone.now()
        if user:
            self.revoked_by = user
        self.save(update_fields=['revoked_at', 'revoked_by'])
    
    @classmethod
    def generate_token(cls):
        """Genera un token único."""
        return str(uuid.uuid4())
