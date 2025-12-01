"""Models for the experiences app."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from core.models import BaseModel
from apps.organizers.models import Organizer


class Experience(BaseModel):
    """Experience model for creating and managing experiences/tours."""
    
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('published', _('Published')),
        ('cancelled', _('Cancelled')),
        ('completed', _('Completed'))
    ]
    
    TYPE_CHOICES = (
        ('activity', _('Activity')),
        ('tour', _('Tour')),
        ('workshop', _('Workshop')),
        ('adventure', _('Adventure')),
        ('other', _('Other')),
    )
    
    title = models.CharField(_("title"), max_length=255)
    slug = models.SlugField(_("slug"), unique=True)
    description = models.TextField(_("description"), blank=True)
    short_description = models.CharField(_("short description"), max_length=255, blank=True)
    
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    
    type = models.CharField(
        _("type"),
        max_length=20,
        choices=TYPE_CHOICES,
        default='activity'
    )
    
    # Organizer
    organizer = models.ForeignKey(
        Organizer,
        on_delete=models.CASCADE,
        related_name='experiences',
        verbose_name=_("organizer")
    )
    
    # Pricing
    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    # Free Tour specific fields
    is_free_tour = models.BooleanField(
        _("is free tour"),
        default=False,
        help_text=_("Whether this is a free tour (users don't pay, organizer pays credit per person)")
    )
    
    credit_per_person = models.DecimalField(
        _("credit per person"),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Cost to organizer per registered person (only for free tours)")
    )
    
    sales_cutoff_hours = models.IntegerField(
        _("sales cutoff hours"),
        default=2,
        validators=[MinValueValidator(1)],
        help_text=_("Hours before tour start time to stop accepting bookings (1-2 hours)")
    )
    
    # Recurrence pattern (JSON field for flexibility)
    recurrence_pattern = models.JSONField(
        _("recurrence pattern"),
        default=dict,
        blank=True,
        help_text=_("Weekly/daily recurrence configuration for tours")
    )
    
    # Location
    location_name = models.CharField(_("location name"), max_length=255, blank=True)
    location_address = models.TextField(_("location address"), blank=True)
    location_latitude = models.DecimalField(
        _("location latitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )
    location_longitude = models.DecimalField(
        _("location longitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )
    
    # Experience details
    duration_minutes = models.PositiveIntegerField(
        _("duration in minutes"),
        null=True,
        blank=True
    )
    max_participants = models.PositiveIntegerField(
        _("max participants"),
        null=True,
        blank=True,
        help_text=_("Maximum number of participants (null = unlimited)")
    )
    min_participants = models.PositiveIntegerField(
        _("min participants"),
        default=1
    )
    
    # Additional info
    included = models.JSONField(
        _("included"),
        default=list,
        blank=True,
        help_text=_("List of what's included in the experience")
    )
    not_included = models.JSONField(
        _("not included"),
        default=list,
        blank=True,
        help_text=_("List of what's not included")
    )
    requirements = models.JSONField(
        _("requirements"),
        default=list,
        blank=True,
        help_text=_("List of requirements for participants")
    )
    itinerary = models.JSONField(
        _("itinerary"),
        default=list,
        blank=True,
        help_text=_("List of itinerary items with time, title, description")
    )
    
    # Images (stored as JSON array of URLs)
    images = models.JSONField(
        _("images"),
        default=list,
        blank=True,
        help_text=_("List of image URLs")
    )
    
    # Categories and tags
    categories = models.JSONField(
        _("categories"),
        default=list,
        blank=True
    )
    tags = models.CharField(_("tags"), max_length=255, blank=True)
    
    # Analytics
    views_count = models.PositiveIntegerField(_("views count"), default=0)
    
    class Meta:
        verbose_name = _("experience")
        verbose_name_plural = _("experiences")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organizer', 'status']),
            models.Index(fields=['is_free_tour', 'status']),
            models.Index(fields=['slug']),
        ]
    
    def __str__(self):
        return self.title


class TourLanguage(BaseModel):
    """Multi-language content for tours."""
    
    LANGUAGE_CHOICES = (
        ('es', _('Spanish')),
        ('en', _('English')),
    )
    
    experience = models.ForeignKey(
        Experience,
        on_delete=models.CASCADE,
        related_name='languages',
        verbose_name=_("experience")
    )
    
    language_code = models.CharField(
        _("language code"),
        max_length=2,
        choices=LANGUAGE_CHOICES
    )
    
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    short_description = models.CharField(_("short description"), max_length=255, blank=True)
    
    is_active = models.BooleanField(
        _("is active"),
        default=True,
        help_text=_("Whether this language version is active (can be blocked)")
    )
    
    class Meta:
        verbose_name = _("tour language")
        verbose_name_plural = _("tour languages")
        unique_together = ['experience', 'language_code']
        indexes = [
            models.Index(fields=['experience', 'language_code']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.experience.title} ({self.get_language_code_display()})"


class TourInstance(BaseModel):
    """Recurring tour instances - specific date/time/language combinations."""
    
    STATUS_CHOICES = (
        ('active', _('Active')),
        ('blocked', _('Blocked')),
        ('cancelled', _('Cancelled')),
    )
    
    LANGUAGE_CHOICES = (
        ('es', _('Spanish')),
        ('en', _('English')),
    )
    
    experience = models.ForeignKey(
        Experience,
        on_delete=models.CASCADE,
        related_name='instances',
        verbose_name=_("experience")
    )
    
    start_datetime = models.DateTimeField(_("start datetime"))
    end_datetime = models.DateTimeField(_("end datetime"))
    
    language = models.CharField(
        _("language"),
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default='es'
    )
    
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    
    max_capacity = models.PositiveIntegerField(
        _("max capacity"),
        null=True,
        blank=True,
        help_text=_("Maximum capacity for this instance (null = uses experience default)")
    )
    
    # Notes for organizer
    notes = models.TextField(_("notes"), blank=True)
    
    class Meta:
        verbose_name = _("tour instance")
        verbose_name_plural = _("tour instances")
        ordering = ['start_datetime']
        indexes = [
            models.Index(fields=['experience', 'start_datetime']),
            models.Index(fields=['status', 'start_datetime']),
            models.Index(fields=['language', 'status']),
        ]
    
    def __str__(self):
        return f"{self.experience.title} - {self.start_datetime.strftime('%Y-%m-%d %H:%M')} ({self.get_language_display()})"
    
    def get_current_bookings_count(self):
        """Get current number of confirmed bookings."""
        from django.db.models import Sum
        result = self.bookings.filter(status='confirmed').aggregate(
            total=Sum('participants_count')
        )
        return result['total'] or 0
    
    def get_available_spots(self):
        """Calculate available spots."""
        if self.max_capacity is None:
            return None  # Unlimited
        return max(0, self.max_capacity - self.get_current_bookings_count())


class TourBooking(BaseModel):
    """Booking for a tour instance (simpler than Event tickets)."""
    
    STATUS_CHOICES = (
        ('confirmed', _('Confirmed')),
        ('cancelled', _('Cancelled')),
    )
    
    tour_instance = models.ForeignKey(
        TourInstance,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_("tour instance")
    )
    
    # User account (reuse account linking logic from tickets)
    user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='tour_bookings',
        verbose_name=_("user"),
        null=True,
        blank=True
    )
    
    # Booking details
    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email"))
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    
    participants_count = models.PositiveIntegerField(
        _("participants count"),
        default=1
    )
    
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='confirmed'
    )
    
    # Link to Order for tracking (amount = 0 for free tours)
    order = models.ForeignKey(
        'events.Order',
        on_delete=models.SET_NULL,
        related_name='tour_bookings',
        verbose_name=_("order"),
        null=True,
        blank=True
    )
    
    # Notes
    notes = models.TextField(_("notes"), blank=True)
    
    class Meta:
        verbose_name = _("tour booking")
        verbose_name_plural = _("tour bookings")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tour_instance', 'status']),
            models.Index(fields=['email']),
            models.Index(fields=['user']),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.tour_instance.experience.title}"


class OrganizerCredit(BaseModel):
    """Track credits charged to organizer for free tour bookings."""
    
    organizer = models.ForeignKey(
        Organizer,
        on_delete=models.CASCADE,
        related_name='credits',
        verbose_name=_("organizer")
    )
    
    tour_booking = models.ForeignKey(
        TourBooking,
        on_delete=models.CASCADE,
        related_name='credits',
        verbose_name=_("tour booking")
    )
    
    amount = models.DecimalField(
        _("amount"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text=_("Credit amount charged (credit_per_person * participants_count)")
    )
    
    # Billing status
    is_billed = models.BooleanField(
        _("is billed"),
        default=False,
        help_text=_("Whether this credit has been billed to the organizer")
    )
    
    billed_at = models.DateTimeField(_("billed at"), null=True, blank=True)
    
    class Meta:
        verbose_name = _("organizer credit")
        verbose_name_plural = _("organizer credits")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organizer', 'is_billed']),
            models.Index(fields=['tour_booking']),
        ]
    
    def __str__(self):
        return f"{self.organizer.name} - ${self.amount} - {self.tour_booking}"

