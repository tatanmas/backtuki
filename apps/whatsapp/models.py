"""Models for WhatsApp integration."""
from django.db import models
from django.utils import timezone
from uuid import uuid4
from core.models import TimeStampedModel, UUIDModel
from django.utils.translation import gettext_lazy as _


class WhatsAppSession(TimeStampedModel, UUIDModel):
    """WhatsApp Web session management."""
    
    STATUS_CHOICES = [
        ('disconnected', _('Desconectado')),
        ('qr_pending', _('Esperando QR')),
        ('connected', _('Conectado')),
        ('expired', _('Expirado')),
    ]
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='disconnected',
        verbose_name=_('Status')
    )
    phone_number = models.CharField(
        max_length=20, 
        blank=True,
        verbose_name=_('Phone Number')
    )
    name = models.CharField(
        max_length=255, 
        blank=True,
        verbose_name=_('Name')
    )
    last_seen = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Last Seen')
    )
    qr_code = models.TextField(
        blank=True,
        help_text=_('Base64 QR code for authentication'),
        verbose_name=_('QR Code')
    )
    
    class Meta:
        verbose_name = _('WhatsApp Session')
        verbose_name_plural = _('WhatsApp Sessions')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.status} - {self.phone_number}"


class WhatsAppMessage(TimeStampedModel, UUIDModel):
    """WhatsApp messages (incoming and outgoing)."""
    
    TYPE_CHOICES = [
        ('in', _('Entrante')),
        ('out', _('Saliente')),
    ]
    
    whatsapp_id = models.CharField(
        max_length=100, 
        unique=True,
        db_index=True,
        verbose_name=_('WhatsApp ID')
    )
    phone = models.CharField(
        max_length=20,
        db_index=True,
        verbose_name=_('Phone')
    )
    type = models.CharField(
        max_length=3, 
        choices=TYPE_CHOICES,
        verbose_name=_('Type')
    )
    content = models.TextField(
        verbose_name=_('Content')
    )
    timestamp = models.DateTimeField(
        verbose_name=_('Timestamp')
    )
    processed = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('Processed')
    )
    chat = models.ForeignKey(
        'whatsapp.WhatsAppChat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messages',
        verbose_name=_('Chat')
    )
    reservation_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Reservation Code')
    )
    is_reservation_related = models.BooleanField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Is Reservation Related')
    )
    linked_reservation_request = models.ForeignKey(
        'whatsapp.WhatsAppReservationRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='linked_messages',
        verbose_name=_('Linked Reservation Request')
    )
    is_automated = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('Is Automated'),
        help_text=_('Indicates if this message was sent automatically by the system/AI')
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Metadata'),
        help_text=_('Additional metadata for the message (e.g., sender_name, sender_phone for group messages)')
    )
    
    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('WhatsApp Message')
        verbose_name_plural = _('WhatsApp Messages')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['phone', 'processed']),
            models.Index(fields=['whatsapp_id']),
            models.Index(fields=['reservation_code']),
            models.Index(fields=['is_reservation_related']),
        ]
    
    def __str__(self):
        return f"{self.type} - {self.phone} - {self.content[:50]}"


class TourOperator(TimeStampedModel, UUIDModel):
    """Tour operator for receiving reservation requests."""
    
    name = models.CharField(
        max_length=255,
        verbose_name=_('Name')
    )
    contact_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Contact Name')
    )
    contact_phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_('Contact Phone')
    )
    whatsapp_number = models.CharField(
        max_length=20,
        blank=True,
        help_text=_('WhatsApp number for receiving notifications (e.g., 56912345678)'),
        verbose_name=_('WhatsApp Number')
    )
    contact_email = models.EmailField(
        blank=True,
        verbose_name=_('Contact Email')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Active')
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('Notes')
    )
    
    # Nueva relación con Organizer
    organizer = models.ForeignKey(
        'organizers.Organizer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tour_operators',
        verbose_name=_('Organizer'),
        help_text=_('Organizer that owns this operator (if auto-created)')
    )
    
    # Grupo de WhatsApp predeterminado para este operador
    default_whatsapp_group = models.ForeignKey(
        'whatsapp.WhatsAppChat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_for_operators',
        verbose_name=_('Default WhatsApp Group'),
        help_text=_('Default WhatsApp group for this operator. New experiences will be linked to this group by default.'),
        limit_choices_to={'type': 'group'}  # Solo grupos
    )
    
    # Flag para indicar si fue creado automáticamente desde un Organizer
    is_system_created = models.BooleanField(
        default=False,
        verbose_name=_('System Created'),
        help_text=_('If True, operator was auto-created from Organizer when first experience was created')
    )
    
    class Meta:
        verbose_name = _('Tour Operator')
        verbose_name_plural = _('Tour Operators')
        ordering = ['name']
    
    def __str__(self):
        return self.name


class WhatsAppReservationRequest(TimeStampedModel, UUIDModel):
    """Reservation request from WhatsApp."""
    
    STATUS_CHOICES = [
        ('received', _('Recibido')),
        ('processing', _('Procesando')),
        ('operator_notified', _('Operador notificado')),
        ('confirmed', _('Confirmada')),
        ('rejected', _('Rechazada')),
        ('timeout', _('Timeout')),
    ]
    
    whatsapp_message = models.ForeignKey(
        WhatsAppMessage,
        on_delete=models.CASCADE,
        related_name='reservation_requests',
        verbose_name=_('WhatsApp Message')
    )
    tour_code = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name=_('Tour Code')
    )
    passengers = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_('Passengers')
    )
    operator = models.ForeignKey(
        TourOperator,
        on_delete=models.PROTECT,
        related_name='reservation_requests',
        verbose_name=_('Operator')
    )
    experience = models.ForeignKey(
        'experiences.Experience',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_reservations',
        verbose_name=_('Experience')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='received',
        db_index=True,
        verbose_name=_('Status')
    )
    timeout_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Timeout At')
    )
    confirmation_token = models.CharField(
        max_length=10,
        blank=True,
        help_text=_('Token for operator confirmation'),
        verbose_name=_('Confirmation Token')
    )
    linked_experience_reservation = models.ForeignKey(
        'experiences.ExperienceReservation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_requests',
        verbose_name=_('Linked Experience Reservation')
    )
    
    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('WhatsApp Reservation Request')
        verbose_name_plural = _('WhatsApp Reservation Requests')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'timeout_at']),
            models.Index(fields=['tour_code', 'status']),
        ]
    
    def __str__(self):
        return f"{self.tour_code} - {self.status}"


class ExperienceOperatorBinding(TimeStampedModel, UUIDModel):
    """Binding between Experience and TourOperator."""
    
    experience = models.ForeignKey(
        'experiences.Experience',
        on_delete=models.CASCADE,
        related_name='operator_bindings',
        verbose_name=_('Experience')
    )
    tour_operator = models.ForeignKey(
        TourOperator,
        on_delete=models.CASCADE,
        related_name='experience_bindings',
        verbose_name=_('Tour Operator')
    )
    priority = models.IntegerField(
        default=0,
        help_text=_('Lower number = higher priority'),
        verbose_name=_('Priority')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Active')
    )
    
    class Meta:
        verbose_name = _('Experience-Operator Binding')
        verbose_name_plural = _('Experience-Operator Bindings')
        ordering = ['experience', 'priority']
        unique_together = [('experience', 'tour_operator')]
    
    def __str__(self):
        return f"{self.experience.title} -> {self.tour_operator.name}"


class ExperienceGroupBinding(TimeStampedModel, UUIDModel):
    """Binding between Experience and WhatsApp Group."""
    
    experience = models.ForeignKey(
        'experiences.Experience',
        on_delete=models.CASCADE,
        related_name='whatsapp_group_bindings',
        verbose_name=_('Experience')
    )
    
    whatsapp_group = models.ForeignKey(
        'whatsapp.WhatsAppChat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='experience_bindings',
        verbose_name=_('WhatsApp Group'),
        limit_choices_to={'type': 'group'},
        help_text=_('WhatsApp group where reservation requests for this experience will be sent')
    )
    
    tour_operator = models.ForeignKey(
        TourOperator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='experience_group_bindings',
        verbose_name=_('Tour Operator'),
        help_text=_('Optional: operator associated with this binding')
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Active'),
        help_text=_('If False, this binding is disabled and will use operator default group')
    )
    
    is_override = models.BooleanField(
        default=False,
        verbose_name=_('Override Default'),
        help_text=_('If True, this binding overrides the operator default group')
    )
    
    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Experience-Group Binding')
        verbose_name_plural = _('Experience-Group Bindings')
        unique_together = [('experience', 'whatsapp_group')]
        indexes = [
            models.Index(fields=['experience', 'is_active']),
            models.Index(fields=['whatsapp_group', 'is_active']),
        ]
    
    def __str__(self):
        group_name = self.whatsapp_group.name if self.whatsapp_group else 'No Group'
        return f"{self.experience.title} -> {group_name}"


class WhatsAppReservationCode(TimeStampedModel, UUIDModel):
    """Unique reservation code generated at checkout."""
    
    STATUS_CHOICES = [
        ('pending', _('Pendiente')),
        ('linked', _('Vinculado')),
        ('expired', _('Expirado')),
    ]
    
    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('Code')
    )
    experience = models.ForeignKey(
        'experiences.Experience',
        on_delete=models.CASCADE,
        related_name='whatsapp_reservation_codes',
        verbose_name=_('Experience')
    )
    checkout_data = models.JSONField(
        default=dict,
        verbose_name=_('Checkout Data'),
        help_text=_('Participants, date, time, pricing, etc.')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
        verbose_name=_('Status')
    )
    linked_reservation = models.ForeignKey(
        'whatsapp.WhatsAppReservationRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reservation_code',
        verbose_name=_('Linked Reservation')
    )
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name=_('Expires At')
    )
    
    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('WhatsApp Reservation Code')
        verbose_name_plural = _('WhatsApp Reservation Codes')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code', 'status']),
            models.Index(fields=['expires_at', 'status']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.status}"
    
    def is_expired(self):
        return timezone.now() > self.expires_at


class WhatsAppChat(TimeStampedModel, UUIDModel):
    """WhatsApp chat (individual or group)."""
    
    TYPE_CHOICES = [
        ('individual', _('Individual')),
        ('group', _('Grupo')),
    ]
    
    chat_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name=_('Chat ID')
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_('Name')
    )
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        db_index=True,
        verbose_name=_('Type')
    )
    assigned_operator = models.ForeignKey(
        TourOperator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_chats',
        verbose_name=_('Assigned Operator')
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_('Active')
    )
    last_message_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Last Message At')
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Metadata')
    )
    # Nuevos campos para funcionalidades de WhatsApp Business
    nickname = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Apodo personalizado para identificar el chat'),
        verbose_name=_('Nickname')
    )
    notes = models.TextField(
        blank=True,
        help_text=_('Notas sobre el chat/cliente'),
        verbose_name=_('Notes')
    )
    whatsapp_name = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Nombre real del contacto en WhatsApp'),
        verbose_name=_('WhatsApp Name')
    )
    profile_picture_url = models.URLField(
        blank=True,
        help_text=_('URL de la foto de perfil del contacto'),
        verbose_name=_('Profile Picture URL')
    )
    unread_count = models.IntegerField(
        default=0,
        db_index=True,
        help_text=_('Número de mensajes sin leer'),
        verbose_name=_('Unread Count')
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text=_('Lista de tags/etiquetas para categorizar el chat'),
        verbose_name=_('Tags')
    )
    # Campos específicos para grupos
    participants = models.JSONField(
        default=list,
        blank=True,
        help_text=_('Lista de participantes del grupo (solo para grupos)'),
        verbose_name=_('Participants')
    )
    group_description = models.TextField(
        blank=True,
        help_text=_('Descripción del grupo (solo para grupos)'),
        verbose_name=_('Group Description')
    )
    
    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('WhatsApp Chat')
        verbose_name_plural = _('WhatsApp Chats')
        ordering = ['-last_message_at']
        indexes = [
            models.Index(fields=['type', 'is_active']),
            models.Index(fields=['assigned_operator', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.type})"

