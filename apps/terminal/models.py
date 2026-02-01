"""Models for terminal bus schedule management."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.utils.text import slugify
from decimal import Decimal

from core.models import BaseModel, TimeStampedModel


class TerminalCompany(BaseModel):
    """Bus company operating in the terminal."""
    
    CONTACT_METHOD_CHOICES = [
        ('internal', _('Internal (Tuki platform)')),
        ('whatsapp', _('WhatsApp')),
        ('external', _('External website')),
    ]
    
    BOOKING_METHOD_CHOICES = [
        ('internal', _('Internal (Tuki platform)')),
        ('external', _('External website')),
        ('whatsapp', _('WhatsApp')),
        ('phone', _('Phone call')),
    ]
    
    name = models.CharField(
        _('name'),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_('Company name (case-insensitive unique)')
    )
    phone = models.CharField(
        _('phone'),
        max_length=20,
        blank=True,
        null=True,
        help_text=_('Contact phone number')
    )
    email = models.EmailField(
        _('email'),
        blank=True,
        null=True,
        help_text=_('Contact email')
    )
    website = models.URLField(
        _('website'),
        blank=True,
        null=True,
        help_text=_('Company website URL')
    )
    logo = models.ImageField(
        _('logo'),
        upload_to='terminal/companies/logos/',
        blank=True,
        null=True,
        help_text=_('Company logo image')
    )
    contact_method = models.CharField(
        _('contact method'),
        max_length=20,
        choices=CONTACT_METHOD_CHOICES,
        default='external',
        help_text=_('Default contact method')
    )
    
    # Booking configuration (v1)
    booking_url = models.URLField(
        _('booking URL'),
        blank=True,
        null=True,
        help_text=_('Direct booking link')
    )
    booking_phone = models.CharField(
        _('booking phone'),
        max_length=20,
        blank=True,
        null=True,
        help_text=_('Phone number for reservations')
    )
    booking_whatsapp = models.CharField(
        _('booking WhatsApp'),
        max_length=20,
        blank=True,
        null=True,
        help_text=_('WhatsApp number for reservations (e.g., +56912345678)')
    )
    booking_method = models.CharField(
        _('booking method'),
        max_length=20,
        choices=BOOKING_METHOD_CHOICES,
        default='external',
        help_text=_('Method used for reservations')
    )
    
    is_active = models.BooleanField(
        _('active'),
        default=True,
        db_index=True,
        help_text=_('Whether this company is active')
    )
    
    class Meta:
        verbose_name = _('Terminal Company')
        verbose_name_plural = _('Terminal Companies')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name


class TerminalRoute(BaseModel):
    """Route between origin and destination."""
    
    origin = models.CharField(
        _('origin'),
        max_length=255,
        db_index=True,
        help_text=_('Origin city/location')
    )
    destination = models.CharField(
        _('destination'),
        max_length=255,
        db_index=True,
        help_text=_('Destination city/location')
    )
    duration = models.CharField(
        _('duration'),
        max_length=50,
        blank=True,
        null=True,
        help_text=_('Approximate duration (e.g., "1h 30min")')
    )
    distance = models.CharField(
        _('distance'),
        max_length=50,
        blank=True,
        null=True,
        help_text=_('Distance (e.g., "65 km")')
    )
    
    class Meta:
        verbose_name = _('Terminal Route')
        verbose_name_plural = _('Terminal Routes')
        unique_together = [['origin', 'destination']]
        indexes = [
            models.Index(fields=['origin', 'destination']),
        ]
    
    def __str__(self):
        return f"{self.origin} → {self.destination}"


class TerminalTrip(BaseModel):
    """Individual bus trip (departure or arrival)."""
    
    TRIP_TYPE_CHOICES = [
        ('departure', _('Departure (from terminal)')),
        ('arrival', _('Arrival (to terminal)')),
    ]
    
    STATUS_CHOICES = [
        ('available', _('Available')),
        ('limited', _('Limited availability')),
        ('sold_out', _('Sold out')),
    ]
    
    company = models.ForeignKey(
        TerminalCompany,
        on_delete=models.CASCADE,
        related_name='trips',
        verbose_name=_('company'),
        help_text=_('Bus company operating this trip')
    )
    route = models.ForeignKey(
        TerminalRoute,
        on_delete=models.CASCADE,
        related_name='trips',
        verbose_name=_('route'),
        help_text=_('Route for this trip')
    )
    trip_type = models.CharField(
        _('trip type'),
        max_length=20,
        choices=TRIP_TYPE_CHOICES,
        db_index=True,
        help_text=_('Whether this is a departure or arrival')
    )
    date = models.DateField(
        _('date'),
        db_index=True,
        help_text=_('Trip date')
    )
    departure_time = models.TimeField(
        _('departure time'),
        blank=True,
        null=True,
        help_text=_('Departure time (only for departures)')
    )
    arrival_time = models.TimeField(
        _('arrival time'),
        blank=True,
        null=True,
        help_text=_('Arrival time (only for arrivals)')
    )
    platform = models.CharField(
        _('platform'),
        max_length=10,
        blank=True,
        null=True,
        help_text=_('Platform number (andén)')
    )
    license_plate = models.CharField(
        _('license plate'),
        max_length=20,
        blank=True,
        null=True,
        help_text=_('Bus license plate (placa)')
    )
    observations = models.TextField(
        _('observations'),
        blank=True,
        null=True,
        help_text=_('Additional observations')
    )
    
    # Seats: nullable in v1 (not used in UI)
    total_seats = models.IntegerField(
        _('total seats'),
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text=_('Total seats (NULL in v1, not shown in UI)')
    )
    available_seats = models.IntegerField(
        _('available seats'),
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text=_('Available seats (NULL in v1, not shown in UI)')
    )
    
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='available',
        db_index=True,
        help_text=_('Trip availability status')
    )
    price = models.DecimalField(
        _('price'),
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('Ticket price')
    )
    currency = models.CharField(
        _('currency'),
        max_length=3,
        default='CLP',
        help_text=_('Currency code (e.g., CLP)')
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        db_index=True,
        help_text=_('If False, hidden from public searches')
    )
    
    class Meta:
        verbose_name = _('Terminal Trip')
        verbose_name_plural = _('Terminal Trips')
        unique_together = [
            ['company', 'route', 'date', 'trip_type', 'departure_time', 'arrival_time']
        ]
        indexes = [
            models.Index(fields=['date', 'trip_type', 'is_active']),
            models.Index(fields=['company', 'date']),
            models.Index(fields=['route', 'date']),
            models.Index(fields=['status', 'is_active']),
        ]
        ordering = ['date', 'departure_time', 'arrival_time']
    
    def __str__(self):
        time_str = self.departure_time.strftime('%H:%M') if self.departure_time else \
                   self.arrival_time.strftime('%H:%M') if self.arrival_time else 'N/A'
        return f"{self.company.name} - {self.route} - {self.date} {time_str}"


class TerminalExcelUpload(TimeStampedModel):
    """Record of Excel file uploads for schedule import."""
    
    UPLOAD_TYPE_CHOICES = [
        ('departures', _('Departures')),
        ('arrivals', _('Arrivals')),
    ]
    
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('processing', _('Processing')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
    ]
    
    file_name = models.CharField(
        _('file name'),
        max_length=255,
        help_text=_('Original filename')
    )
    file_path = models.FileField(
        _('file'),
        upload_to='terminal/uploads/',
        help_text=_('Uploaded Excel file')
    )
    upload_type = models.CharField(
        _('upload type'),
        max_length=20,
        choices=UPLOAD_TYPE_CHOICES,
        help_text=_('Whether this is departures or arrivals')
    )
    date_range_start = models.DateField(
        _('date range start'),
        help_text=_('Start date of the schedule range')
    )
    date_range_end = models.DateField(
        _('date range end'),
        help_text=_('End date of the schedule range')
    )
    processed_sheets = models.JSONField(
        _('processed sheets'),
        default=list,
        blank=True,
        help_text=_('List of sheet names that were processed')
    )
    trips_created = models.IntegerField(
        _('trips created'),
        default=0,
        help_text=_('Number of trips created')
    )
    trips_updated = models.IntegerField(
        _('trips updated'),
        default=0,
        help_text=_('Number of trips updated')
    )
    errors = models.JSONField(
        _('errors'),
        default=list,
        blank=True,
        help_text=_('List of errors encountered during processing')
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
        help_text=_('Processing status')
    )
    uploaded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='terminal_uploads',
        verbose_name=_('uploaded by'),
        help_text=_('User who uploaded the file')
    )
    
    class Meta:
        verbose_name = _('Terminal Excel Upload')
        verbose_name_plural = _('Terminal Excel Uploads')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['upload_type', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.file_name} - {self.get_upload_type_display()} ({self.get_status_display()})"


class TerminalDestination(BaseModel):
    """Destination detected automatically from routes or created manually."""
    
    name = models.CharField(
        _('name'),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_('Destination name (unique)')
    )
    slug = models.SlugField(
        _('slug'),
        unique=True,
        max_length=255,
        db_index=True,
        help_text=_('URL-friendly identifier')
    )
    description = models.TextField(
        _('description'),
        blank=True,
        null=True,
        help_text=_('Destination description')
    )
    image = models.ImageField(
        _('image'),
        upload_to='terminal/destinations/',
        blank=True,
        null=True,
        help_text=_('Destination image')
    )
    region = models.CharField(
        _('region'),
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Region name (e.g., "Aysén")')
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        db_index=True,
        help_text=_('Whether this destination is active')
    )
    created_from_excel = models.BooleanField(
        _('created from excel'),
        default=False,
        help_text=_('Indicates if this destination was created automatically from Excel upload')
    )
    
    class Meta:
        verbose_name = _('Terminal Destination')
        verbose_name_plural = _('Terminal Destinations')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]
    
    def save(self, *args, **kwargs):
        """Auto-generate slug if not provided."""
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name


class TerminalAdvertisingSpace(BaseModel):
    """Configurable advertising spaces in the terminal website."""
    
    SPACE_TYPE_CHOICES = [
        ('hero_slider', _('Hero Slider')),
        ('featured_experiences', _('Featured Experiences')),
        ('destination_banner', _('Destination Banner')),
        ('experience_card', _('Experience Card')),
    ]
    
    CONTENT_TYPE_CHOICES = [
        ('experience', _('Experience')),
        ('banner', _('Banner')),
        ('custom', _('Custom')),
    ]
    
    space_type = models.CharField(
        _('space type'),
        max_length=50,
        choices=SPACE_TYPE_CHOICES,
        db_index=True,
        help_text=_('Type of advertising space')
    )
    position = models.CharField(
        _('position'),
        max_length=255,
        db_index=True,
        help_text=_('Unique position identifier (e.g., "home_featured_1", "destination_chaiten_banner")')
    )
    destination = models.ForeignKey(
        TerminalDestination,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='advertising_spaces',
        verbose_name=_('destination'),
        help_text=_('Destination this space applies to (if applicable)')
    )
    route_origin = models.CharField(
        _('route origin'),
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text=_('Origin of route (e.g., "Coyhaique")')
    )
    route_destination = models.CharField(
        _('route destination'),
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text=_('Destination of route (e.g., "Chaitén")')
    )
    content_type = models.CharField(
        _('content type'),
        max_length=20,
        choices=CONTENT_TYPE_CHOICES,
        help_text=_('Type of content: experience, banner, or custom')
    )
    experience = models.ForeignKey(
        'experiences.Experience',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='terminal_advertising_spaces',
        verbose_name=_('experience'),
        help_text=_('Experience to display (if content_type is "experience")')
    )
    banner_image = models.ImageField(
        _('banner image'),
        upload_to='terminal/advertising/banners/',
        blank=True,
        null=True,
        help_text=_('Banner image (if content_type is "banner")')
    )
    banner_title = models.CharField(
        _('banner title'),
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Banner title')
    )
    banner_subtitle = models.CharField(
        _('banner subtitle'),
        max_length=500,
        blank=True,
        null=True,
        help_text=_('Banner subtitle')
    )
    banner_cta_text = models.CharField(
        _('banner cta text'),
        max_length=100,
        blank=True,
        null=True,
        help_text=_('Banner call-to-action text')
    )
    banner_cta_url = models.URLField(
        _('banner cta url'),
        blank=True,
        null=True,
        help_text=_('Banner call-to-action URL')
    )
    order = models.IntegerField(
        _('order'),
        default=0,
        db_index=True,
        help_text=_('Display order')
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        db_index=True,
        help_text=_('Whether this space is active')
    )
    display_from = models.DateTimeField(
        _('display from'),
        blank=True,
        null=True,
        db_index=True,
        help_text=_('Start date/time for display')
    )
    display_until = models.DateTimeField(
        _('display until'),
        blank=True,
        null=True,
        db_index=True,
        help_text=_('End date/time for display')
    )
    
    class Meta:
        verbose_name = _('Terminal Advertising Space')
        verbose_name_plural = _('Terminal Advertising Spaces')
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['space_type', 'is_active']),
            models.Index(fields=['destination', 'is_active']),
            models.Index(fields=['position']),
            models.Index(fields=['display_from', 'display_until']),
        ]
    
    def __str__(self):
        return f"{self.get_space_type_display()} - {self.position}"


class TerminalAdvertisingInteraction(TimeStampedModel):
    """Tracking of interactions with advertising spaces."""
    
    INTERACTION_TYPE_CHOICES = [
        ('view', _('View')),
        ('click', _('Click')),
        ('impression', _('Impression')),
    ]
    
    advertising_space = models.ForeignKey(
        TerminalAdvertisingSpace,
        on_delete=models.CASCADE,
        related_name='interactions',
        verbose_name=_('advertising space'),
        help_text=_('The advertising space that was interacted with')
    )
    interaction_type = models.CharField(
        _('interaction type'),
        max_length=20,
        choices=INTERACTION_TYPE_CHOICES,
        db_index=True,
        help_text=_('Type of interaction')
    )
    user_ip = models.GenericIPAddressField(
        _('user ip'),
        null=True,
        blank=True,
        help_text=_('User IP address')
    )
    user_agent = models.TextField(
        _('user agent'),
        blank=True,
        null=True,
        help_text=_('User agent string')
    )
    referrer = models.URLField(
        _('referrer'),
        blank=True,
        null=True,
        help_text=_('Referrer URL')
    )
    destination = models.CharField(
        _('destination'),
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Destination from which the interaction occurred')
    )
    
    class Meta:
        verbose_name = _('Terminal Advertising Interaction')
        verbose_name_plural = _('Terminal Advertising Interactions')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['advertising_space', 'interaction_type']),
            models.Index(fields=['interaction_type', 'created_at']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.advertising_space} - {self.get_interaction_type_display()} - {self.created_at}"


class TerminalDestinationExperienceConfig(BaseModel):
    """Configuration of experiences for each destination."""
    
    destination = models.ForeignKey(
        TerminalDestination,
        on_delete=models.CASCADE,
        related_name='experience_configs',
        verbose_name=_('destination'),
        help_text=_('Destination this configuration applies to')
    )
    experience = models.ForeignKey(
        'experiences.Experience',
        on_delete=models.CASCADE,
        related_name='terminal_destination_configs',
        verbose_name=_('experience'),
        help_text=_('Experience to display for this destination')
    )
    is_featured = models.BooleanField(
        _('is featured'),
        default=False,
        db_index=True,
        help_text=_('Whether this experience appears in featured section')
    )
    order = models.IntegerField(
        _('order'),
        default=0,
        db_index=True,
        help_text=_('Display order for featured experiences')
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        db_index=True,
        help_text=_('Whether this configuration is active')
    )
    
    class Meta:
        verbose_name = _('Terminal Destination Experience Config')
        verbose_name_plural = _('Terminal Destination Experience Configs')
        unique_together = [['destination', 'experience']]
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['destination', 'is_featured', 'is_active']),
            models.Index(fields=['is_featured', 'order']),
        ]
    
    def __str__(self):
        return f"{self.destination.name} - {self.experience.title}"

