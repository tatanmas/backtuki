"""
Modelos para el sistema de sincronización WooCommerce

Estos modelos gestionan las configuraciones de sincronización,
logs de ejecución y estadísticas del sistema.
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


class SyncConfiguration(models.Model):
    """
    Configuración de sincronización para un evento específico
    """
    
    STATUS_CHOICES = [
        ('active', 'Activo'),
        ('paused', 'Pausado'),
        ('disabled', 'Deshabilitado'),
        ('error', 'Error'),
    ]
    
    FREQUENCY_CHOICES = [
        ('manual', 'Manual'),
        ('hourly', 'Cada hora'),
        ('daily', 'Diario'),
        ('weekly', 'Semanal'),
        ('monthly', 'Mensual'),
    ]
    
    # Identificación
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=255,
        help_text="Nombre descriptivo para esta sincronización"
    )
    
    # Configuración WooCommerce
    woocommerce_product_id = models.PositiveIntegerField(
        help_text="ID del producto/evento en WooCommerce"
    )
    
    # Configuración del evento en Django
    event_name = models.CharField(
        max_length=255,
        help_text="Nombre que tendrá el evento en Django"
    )
    organizer_email = models.EmailField(
        help_text="Email del organizador (se creará si no existe)"
    )
    organizer_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Nombre del organizador (opcional)"
    )
    
    # Configuración financiera
    service_fee_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=10.0,
        help_text="Porcentaje de cargo por servicio (0-100)"
    )
    
    # Configuración de sincronización
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='daily',
        help_text="Frecuencia de sincronización"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        help_text="Estado de la sincronización"
    )
    
    # Configuración adicional del evento
    event_description = models.TextField(
        blank=True,
        help_text="Descripción del evento (opcional)"
    )
    event_start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha de inicio del evento (opcional)"
    )
    event_end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha de fin del evento (opcional)"
    )
    
    # Configuración del TicketTier
    ticket_tier_name = models.CharField(
        max_length=255,
        default='General',
        help_text="Nombre del TicketTier que se creará"
    )
    
    # Metadatos
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sync_configurations_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Estadísticas
    last_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última vez que se ejecutó la sincronización"
    )
    last_sync_status = models.CharField(
        max_length=20,
        blank=True,
        help_text="Estado de la última sincronización"
    )
    total_syncs = models.PositiveIntegerField(
        default=0,
        help_text="Número total de sincronizaciones ejecutadas"
    )
    successful_syncs = models.PositiveIntegerField(
        default=0,
        help_text="Número de sincronizaciones exitosas"
    )
    
    # Referencias a objetos creados
    django_event_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="ID del evento creado en Django"
    )
    django_organizer_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="ID del organizador en Django"
    )
    django_form_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="ID del formulario creado en Django"
    )
    
    class Meta:
        verbose_name = "Configuración de Sincronización"
        verbose_name_plural = "Configuraciones de Sincronización"
        ordering = ['-created_at']
        unique_together = ['woocommerce_product_id', 'organizer_email']
    
    def __str__(self):
        return f"{self.name} (WC#{self.woocommerce_product_id})"
    
    @property
    def success_rate(self):
        """Calcula la tasa de éxito de las sincronizaciones"""
        if self.total_syncs == 0:
            return 0
        return (self.successful_syncs / self.total_syncs) * 100
    
    def is_due_for_sync(self):
        """Determina si la sincronización debe ejecutarse"""
        if self.status != 'active':
            return False
        
        if self.frequency == 'manual':
            return False
        
        if not self.last_sync_at:
            return True
        
        now = timezone.now()
        time_diff = now - self.last_sync_at
        
        if self.frequency == 'hourly':
            return time_diff.total_seconds() >= 3600
        elif self.frequency == 'daily':
            return time_diff.days >= 1
        elif self.frequency == 'weekly':
            return time_diff.days >= 7
        elif self.frequency == 'monthly':
            return time_diff.days >= 30
        
        return False


class SyncExecution(models.Model):
    """
    Registro de ejecución de una sincronización
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('running', 'Ejecutándose'),
        ('success', 'Exitoso'),
        ('failed', 'Fallido'),
        ('cancelled', 'Cancelado'),
    ]
    
    TRIGGER_CHOICES = [
        ('scheduled', 'Programado'),
        ('manual', 'Manual'),
        ('api', 'API'),
        ('retry', 'Reintento'),
    ]
    
    # Identificación
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(
        SyncConfiguration,
        on_delete=models.CASCADE,
        related_name='executions'
    )
    
    # Estado de ejecución
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        default='scheduled'
    )
    
    # Tiempos
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    
    # Resultados
    orders_processed = models.PositiveIntegerField(default=0)
    tickets_processed = models.PositiveIntegerField(default=0)
    orders_created = models.PositiveIntegerField(default=0)
    orders_updated = models.PositiveIntegerField(default=0)
    tickets_created = models.PositiveIntegerField(default=0)
    tickets_updated = models.PositiveIntegerField(default=0)
    
    # Información adicional
    error_message = models.TextField(
        blank=True,
        help_text="Mensaje de error si la sincronización falló"
    )
    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="ID de la tarea de Celery"
    )
    
    # Metadatos
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Usuario que disparó la sincronización (si fue manual)"
    )
    
    class Meta:
        verbose_name = "Ejecución de Sincronización"
        verbose_name_plural = "Ejecuciones de Sincronización"
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.configuration.name} - {self.started_at.strftime('%Y-%m-%d %H:%M')}"
    
    def save(self, *args, **kwargs):
        """Calcular duración al guardar"""
        if self.finished_at and self.started_at:
            duration = self.finished_at - self.started_at
            self.duration_seconds = int(duration.total_seconds())
        super().save(*args, **kwargs)


class SyncCredentials(models.Model):
    """
    Credenciales SSH para conectar a WooCommerce
    
    Nota: Las credenciales sensibles se almacenan en variables de entorno,
    este modelo solo guarda referencias y configuraciones no sensibles.
    """
    
    # Identificación
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Nombre descriptivo para estas credenciales"
    )
    
    # Configuración SSH (no sensible)
    ssh_host = models.CharField(max_length=255)
    ssh_port = models.PositiveIntegerField(default=22)
    ssh_username = models.CharField(max_length=255)
    
    # Configuración MySQL (no sensible)
    mysql_host = models.CharField(max_length=255, default='localhost')
    mysql_port = models.PositiveIntegerField(default=3306)
    mysql_database = models.CharField(max_length=255)
    mysql_username = models.CharField(max_length=255)
    
    # Configuración
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    
    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Credenciales de Sincronización"
        verbose_name_plural = "Credenciales de Sincronización"
        ordering = ['-is_default', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.ssh_host})"
    
    def save(self, *args, **kwargs):
        """Asegurar que solo hay un conjunto de credenciales por defecto"""
        if self.is_default:
            SyncCredentials.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)
