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
        max_length=50,
        db_index=True,
        verbose_name=_('Phone'),
        help_text=_('Phone number or group ID (format: XXXXXXXXXXX-XXXXXXXXXX for groups)')
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
    # Media and reply support (enterprise)
    media_type = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Media Type'),
        help_text=_('WhatsApp message type: chat, ptt, audio, image, video, document, sticker, etc.')
    )
    reply_to_whatsapp_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Reply To WhatsApp ID'),
        help_text=_('WhatsApp ID of the message this is a reply to')
    )
    media_url = models.URLField(
        max_length=2048,
        null=True,
        blank=True,
        verbose_name=_('Media URL'),
        help_text=_('URL to media file if uploaded to storage')
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
            models.Index(fields=['reply_to_whatsapp_id']),
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
    last_message_preview = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Preview of last message for chat list (without opening)'),
        verbose_name=_('Last Message Preview')
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


class WhatsAppReservationRequest(TimeStampedModel, UUIDModel):
    """Reservation request from WhatsApp."""
    
    STATUS_CHOICES = [
        ('received', _('Recibido')),
        ('processing', _('Procesando')),
        ('operator_notified', _('Operador notificado')),
        ('availability_confirmed', _('Disponibilidad confirmada')),
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
        null=True,
        blank=True,
        related_name='reservation_requests',
        verbose_name=_('Operator'),
        help_text=_('Nullable when experience has no operator; assign manually later')
    )
    experience = models.ForeignKey(
        'experiences.Experience',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_reservations',
        verbose_name=_('Experience')
    )
    accommodation = models.ForeignKey(
        'accommodations.Accommodation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_reservations',
        verbose_name=_('Accommodation'),
        help_text=_('Accommodation for WhatsApp reservation (when product is accommodation)')
    )
    status = models.CharField(
        max_length=30,
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
    linked_accommodation_reservation = models.ForeignKey(
        'accommodations.AccommodationReservation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_requests',
        verbose_name=_('Linked Accommodation Reservation')
    )
    car = models.ForeignKey(
        'car_rental.Car',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_reservations',
        verbose_name=_('Car'),
        help_text=_('Car for WhatsApp reservation (when product is car_rental)')
    )
    linked_car_rental_reservation = models.ForeignKey(
        'car_rental.CarReservation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_requests',
        verbose_name=_('Linked Car Rental Reservation')
    )
    # 🚀 ENTERPRISE: Platform flow for full audit trail (experience, accommodation, car_rental WhatsApp)
    flow = models.ForeignKey(
        'core.PlatformFlow',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_reservation_requests',
        verbose_name=_('Platform Flow'),
        help_text=_('Platform flow tracking this WhatsApp reservation (all steps from request to payment)'),
    )

    # Campos para tracking del flujo de pago
    payment_link = models.URLField(
        blank=True,
        verbose_name=_('Payment Link'),
        help_text=_('Generated payment link sent to customer')
    )
    payment_link_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Payment Link Sent At')
    )
    payment_received_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Payment Received At')
    )
    ticket_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Ticket Sent At')
    )
    
    # Datos del cliente recolectados
    customer_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Customer Data'),
        help_text=_('Additional customer data collected during conversation')
    )
    
    # Respuestas del operador
    operator_response = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Operator Response'),
        help_text=_('Last response from operator')
    )
    operator_responded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Operator Responded At')
    )
    
    # Métricas de tiempo
    customer_notified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Customer Notified At'),
        help_text=_('When customer was notified of result')
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
    
    def get_response_time_seconds(self):
        """Calcular tiempo de respuesta del operador."""
        if self.operator_responded_at and self.created_at:
            delta = self.operator_responded_at - self.created_at
            return delta.total_seconds()
        return None


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


class AccommodationOperatorBinding(TimeStampedModel, UUIDModel):
    """Binding between Accommodation and TourOperator (same pattern as Experience)."""
    accommodation = models.ForeignKey(
        'accommodations.Accommodation',
        on_delete=models.CASCADE,
        related_name='operator_bindings',
        verbose_name=_('Accommodation')
    )
    tour_operator = models.ForeignKey(
        TourOperator,
        on_delete=models.CASCADE,
        related_name='accommodation_bindings',
        verbose_name=_('Tour Operator')
    )
    priority = models.IntegerField(
        default=0,
        help_text=_('Lower number = higher priority'),
        verbose_name=_('Priority')
    )
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))

    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Accommodation-Operator Binding')
        verbose_name_plural = _('Accommodation-Operator Bindings')
        ordering = ['accommodation', 'priority']
        unique_together = [('accommodation', 'tour_operator')]

    def __str__(self):
        return f"{self.accommodation.title} -> {self.tour_operator.name}"


class AccommodationGroupBinding(TimeStampedModel, UUIDModel):
    """Binding between Accommodation and WhatsApp Group (same pattern as Experience)."""
    accommodation = models.ForeignKey(
        'accommodations.Accommodation',
        on_delete=models.CASCADE,
        related_name='whatsapp_group_bindings',
        verbose_name=_('Accommodation')
    )
    whatsapp_group = models.ForeignKey(
        'whatsapp.WhatsAppChat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accommodation_bindings',
        verbose_name=_('WhatsApp Group'),
        limit_choices_to={'type': 'group'}
    )
    tour_operator = models.ForeignKey(
        TourOperator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accommodation_group_bindings',
        verbose_name=_('Tour Operator')
    )
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    is_override = models.BooleanField(default=False, verbose_name=_('Override Default'))

    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Accommodation-Group Binding')
        verbose_name_plural = _('Accommodation-Group Bindings')
        unique_together = [('accommodation', 'whatsapp_group')]
        indexes = [
            models.Index(fields=['accommodation', 'is_active']),
            models.Index(fields=['whatsapp_group', 'is_active']),
        ]

    def __str__(self):
        group_name = self.whatsapp_group.name if self.whatsapp_group else 'No Group'
        return f"{self.accommodation.title} -> {group_name}"


class CarOperatorBinding(TimeStampedModel, UUIDModel):
    """Binding between Car (car_rental) and TourOperator."""
    car = models.ForeignKey(
        'car_rental.Car',
        on_delete=models.CASCADE,
        related_name='operator_bindings',
        verbose_name=_('Car')
    )
    tour_operator = models.ForeignKey(
        TourOperator,
        on_delete=models.CASCADE,
        related_name='car_bindings',
        verbose_name=_('Tour Operator')
    )
    priority = models.IntegerField(default=0, help_text=_('Lower number = higher priority'), verbose_name=_('Priority'))
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))

    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Car-Operator Binding')
        verbose_name_plural = _('Car-Operator Bindings')
        ordering = ['car', 'priority']
        unique_together = [('car', 'tour_operator')]

    def __str__(self):
        return f"{self.car.title} -> {self.tour_operator.name}"


class CarGroupBinding(TimeStampedModel, UUIDModel):
    """Binding between Car and WhatsApp Group."""
    car = models.ForeignKey(
        'car_rental.Car',
        on_delete=models.CASCADE,
        related_name='whatsapp_group_bindings',
        verbose_name=_('Car')
    )
    whatsapp_group = models.ForeignKey(
        'whatsapp.WhatsAppChat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='car_bindings',
        verbose_name=_('WhatsApp Group'),
        limit_choices_to={'type': 'group'}
    )
    tour_operator = models.ForeignKey(
        TourOperator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='car_group_bindings',
        verbose_name=_('Tour Operator')
    )
    is_active = models.BooleanField(default=True, verbose_name=_('Active'))
    is_override = models.BooleanField(default=False, verbose_name=_('Override Default'))

    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Car-Group Binding')
        verbose_name_plural = _('Car-Group Bindings')
        unique_together = [('car', 'whatsapp_group')]
        indexes = [
            models.Index(fields=['car', 'is_active']),
            models.Index(fields=['whatsapp_group', 'is_active']),
        ]

    def __str__(self):
        group_name = self.whatsapp_group.name if self.whatsapp_group else 'No Group'
        return f"{self.car.title} -> {group_name}"


class WhatsAppReservationCode(TimeStampedModel, UUIDModel):
    """Unique reservation code generated at checkout (experience or accommodation)."""
    
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
        verbose_name=_('Experience'),
        null=True,
        blank=True,
        help_text=_('Experience for experience codes. Null when accommodation is set.')
    )
    accommodation = models.ForeignKey(
        'accommodations.Accommodation',
        on_delete=models.CASCADE,
        related_name='whatsapp_reservation_codes',
        verbose_name=_('Accommodation'),
        null=True,
        blank=True,
        help_text=_('Accommodation for accommodation codes. Null when experience/car is set.')
    )
    car = models.ForeignKey(
        'car_rental.Car',
        on_delete=models.CASCADE,
        related_name='whatsapp_reservation_codes',
        verbose_name=_('Car'),
        null=True,
        blank=True,
        help_text=_('Car for car_rental codes. Null when experience/accommodation is set.')
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
    # 🚀 ENTERPRISE: Flow started when code was generated (so superadmin sees intent even if message never sent)
    flow = models.ForeignKey(
        'core.PlatformFlow',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_reservation_codes',
        verbose_name=_('Platform Flow'),
        help_text=_('Flow started at code generation; reused when WhatsApp message is received.')
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


class OperatorMessageTemplate(TimeStampedModel, UUIDModel):
    """
    Customizable message templates for each operator.
    
    Variables disponibles:
    - {{contacto}} - Nombre del contacto del operador
    - {{experiencia}} - Nombre de la experiencia/tour
    - {{fecha}} - Fecha de la reserva (ej: "15 de marzo de 2026")
    - {{hora}} - Hora de la reserva (ej: "10:00")
    - {{pasajeros}} - Número total de pasajeros
    - {{adultos}} - Número de adultos
    - {{ninos}} - Número de niños
    - {{infantes}} - Número de infantes
    - {{precio}} - Precio total formateado (ej: "$45.000")
    - {{nombre_cliente}} - Nombre del cliente
    - {{telefono_cliente}} - Teléfono del cliente
    - {{codigo}} - Código de reserva
    - {{link_pago}} - Link de pago (si aplica)
    """
    
    MESSAGE_TYPE_CHOICES = [
        ('reservation_request', _('Solicitud de reserva al operador')),
        ('customer_confirmation', _('Confirmación al cliente')),
        ('customer_rejection', _('Rechazo al cliente')),
        ('customer_waiting', _('Esperando confirmación del operador')),
        ('payment_link', _('Link de pago al cliente')),
        ('payment_confirmed', _('Pago confirmado al cliente')),
        ('ticket_info', _('Información del ticket')),
        ('reminder', _('Recordatorio al operador')),
    ]
    
    operator = models.ForeignKey(
        TourOperator,
        on_delete=models.CASCADE,
        related_name='message_templates',
        verbose_name=_('Operator')
    )
    message_type = models.CharField(
        max_length=30,
        choices=MESSAGE_TYPE_CHOICES,
        db_index=True,
        verbose_name=_('Message Type')
    )
    template = models.TextField(
        verbose_name=_('Template'),
        help_text=_('Use {{variable}} for dynamic content')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Active')
    )
    
    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Operator Message Template')
        verbose_name_plural = _('Operator Message Templates')
        unique_together = [('operator', 'message_type')]
        ordering = ['operator', 'message_type']
    
    def __str__(self):
        return f"{self.operator.name} - {self.get_message_type_display()}"
    
    def render(self, context: dict) -> str:
        """Render template with given context variables."""
        result = self.template
        for key, value in context.items():
            result = result.replace(f"{{{{{key}}}}}", str(value) if value else '')
        return result


class WhatsAppReservationMessageConfig(TimeStampedModel):
    """
    Singleton config for platform-wide WhatsApp reservation flow message templates.
    Editable from Super Admin. Keys = message_type (reservation_request, customer_waiting, etc.).
    If a key is missing or empty, the code falls back to operator template then DEFAULT_TEMPLATES.
    """
    CONFIG_KEY = "default"

    config_key = models.CharField(
        _("config key"),
        max_length=50,
        unique=True,
        default=CONFIG_KEY,
        editable=False,
    )
    templates = models.JSONField(
        _("templates"),
        default=dict,
        blank=True,
        help_text=_(
            'Dict message_type -> template text, e.g. {"reservation_request": "Nueva solicitud...", '
            '"customer_waiting": "Estimado/a {{nombre_cliente}}..."}. '
            'Use {{variable}} for placeholders.'
        ),
    )

    class Meta:
        app_label = 'whatsapp'
        verbose_name = _("WhatsApp reservation message config")
        verbose_name_plural = _("WhatsApp reservation message configs")

    def __str__(self):
        return f"Reservation messages ({len(self.templates or {})} types)"


class OperatorRequiredFields(TimeStampedModel, UUIDModel):
    """
    Campos requeridos por cada operador para completar una reserva.
    Ej: nombre completo, RUT, email, etc.
    """
    
    FIELD_TYPE_CHOICES = [
        ('text', _('Texto')),
        ('number', _('Número')),
        ('email', _('Email')),
        ('phone', _('Teléfono')),
        ('rut', _('RUT/Identificación')),
        ('date', _('Fecha')),
        ('select', _('Selección')),
    ]
    
    operator = models.ForeignKey(
        TourOperator,
        on_delete=models.CASCADE,
        related_name='required_fields',
        verbose_name=_('Operator')
    )
    field_name = models.CharField(
        max_length=50,
        verbose_name=_('Field Name'),
        help_text=_('Internal field identifier (e.g., "rut", "full_name")')
    )
    display_name = models.CharField(
        max_length=100,
        verbose_name=_('Display Name'),
        help_text=_('Name shown to customer (e.g., "RUT", "Nombre completo")')
    )
    field_type = models.CharField(
        max_length=20,
        choices=FIELD_TYPE_CHOICES,
        default='text',
        verbose_name=_('Field Type')
    )
    is_required = models.BooleanField(
        default=True,
        verbose_name=_('Required')
    )
    options = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Options'),
        help_text=_('Options for select fields')
    )
    order = models.IntegerField(
        default=0,
        verbose_name=_('Order')
    )
    
    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Operator Required Field')
        verbose_name_plural = _('Operator Required Fields')
        unique_together = [('operator', 'field_name')]
        ordering = ['operator', 'order']
    
    def __str__(self):
        return f"{self.operator.name} - {self.display_name}"


class ConversationState(TimeStampedModel, UUIDModel):
    """
    Estado de conversación para flujos multi-turno.
    Mantiene el contexto de la conversación con un cliente.
    """
    
    STATE_CHOICES = [
        ('idle', _('Inactivo')),
        ('awaiting_reservation_code', _('Esperando código de reserva')),
        ('awaiting_customer_info', _('Esperando información del cliente')),
        ('awaiting_operator_response', _('Esperando respuesta del operador')),
        ('awaiting_payment', _('Esperando pago')),
        ('completed', _('Completado')),
        ('cancelled', _('Cancelado')),
    ]
    
    chat = models.OneToOneField(
        'whatsapp.WhatsAppChat',
        on_delete=models.CASCADE,
        related_name='conversation_state',
        verbose_name=_('Chat')
    )
    state = models.CharField(
        max_length=30,
        choices=STATE_CHOICES,
        default='idle',
        db_index=True,
        verbose_name=_('State')
    )
    current_reservation = models.ForeignKey(
        'whatsapp.WhatsAppReservationRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversation_states',
        verbose_name=_('Current Reservation')
    )
    context = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Context'),
        help_text=_('Additional context data for the conversation')
    )
    pending_fields = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Pending Fields'),
        help_text=_('List of required fields still pending')
    )
    collected_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Collected Data'),
        help_text=_('Data collected from customer during conversation')
    )
    last_activity = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Last Activity')
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Expires At')
    )
    
    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Conversation State')
        verbose_name_plural = _('Conversation States')
        indexes = [
            models.Index(fields=['state', 'expires_at']),
        ]
    
    def __str__(self):
        return f"{self.chat.name} - {self.get_state_display()}"
    
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False


class GroupOutreachConfig(TimeStampedModel, UUIDModel):
    """
    Configuración de outreach (primer mensaje) por grupo de WhatsApp.
    Permite activar/desactivar el envío automático de mensajes iniciales a participantes
    que aún no tienen conversación con nosotros, con mensajes randomizados y delays humanos
    para reducir riesgo de detección como spam.
    """
    group = models.OneToOneField(
        WhatsAppChat,
        on_delete=models.CASCADE,
        related_name='outreach_config',
        limit_choices_to={'type': 'group'},
        verbose_name=_('Group'),
    )
    enabled = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('Enabled'),
        help_text=_('When enabled, the system will send first messages to eligible participants.'),
    )
    message_templates = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Message templates'),
        help_text=_('List of message texts. One will be chosen at random per send.'),
    )
    exclude_numbers = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Exclude numbers'),
        help_text=_('Phone numbers to never message (e.g. ["56912345678"]).'),
    )
    min_delay_seconds = models.PositiveIntegerField(
        default=120,
        verbose_name=_('Min delay (seconds)'),
        help_text=_('Minimum seconds between two sends (e.g. 600 for 10 min base).'),
    )
    max_delay_seconds = models.PositiveIntegerField(
        default=300,
        verbose_name=_('Max delay (seconds)'),
        help_text=_('Maximum seconds between two sends (e.g. 660 = 10 min + 0–60 s jitter).'),
    )
    max_per_run = models.PositiveSmallIntegerField(
        default=1,
        verbose_name=_('Max per run'),
        help_text=_('Max first messages to send per scheduled run.'),
    )
    skip_saved_contacts = models.BooleanField(
        default=True,
        verbose_name=_('Skip saved contacts'),
        help_text=_('Do not send to numbers that are in your phone contacts.'),
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Last run at'),
    )
    cached_eligible_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Cached eligible count'),
        help_text=_('Last computed count of eligible participants; refreshed on demand.'),
    )
    cached_eligible_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Cached eligible at'),
        help_text=_('When eligible_count was last computed.'),
    )
    cached_participants_total = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Cached participants total'),
        help_text=_('Total participants in group when eligible count was computed.'),
    )
    cached_eligible_participants = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Cached eligible participants'),
        help_text=_('List of {id, phone_normalized} for eligible participants; used for sending without re-fetching from Node.'),
    )

    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Group outreach config')
        verbose_name_plural = _('Group outreach configs')

    def __str__(self):
        return f'{self.group.name} (outreach: {"on" if self.enabled else "off"})'


class GroupOutreachSent(TimeStampedModel, UUIDModel):
    """Registro de primer mensaje de outreach enviado a un participante de un grupo."""
    config = models.ForeignKey(
        GroupOutreachConfig,
        on_delete=models.CASCADE,
        related_name='sent_records',
        verbose_name=_('Outreach config'),
    )
    participant_id = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_('Participant ID'),
        help_text=_('WhatsApp participant id (e.g. 569xxx@c.us or xxx@lid).'),
    )
    phone_normalized = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        verbose_name=_('Phone normalized'),
        help_text=_('Digits-only phone for exclude lookups.'),
    )
    message_used = models.TextField(
        blank=True,
        verbose_name=_('Message used'),
        help_text=_('The message text that was sent.'),
    )
    message_index = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Message template index'),
    )
    sent_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name=_('Sent at'),
    )

    class Meta:
        app_label = 'whatsapp'
        verbose_name = _('Group outreach sent')
        verbose_name_plural = _('Group outreach sent')
        unique_together = [('config', 'participant_id')]
        indexes = [
            models.Index(fields=['config', 'sent_at']),
        ]

    def __str__(self):
        return f'{self.config.group.name} -> {self.participant_id} @ {self.sent_at}'

