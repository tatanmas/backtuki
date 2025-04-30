"""Models for the events app."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import BaseModel, TimeStampedModel
from core.utils import get_upload_path

User = get_user_model()


class Location(BaseModel):
    """Location model for events."""
    
    name = models.CharField(_("name"), max_length=255)
    address = models.CharField(_("address"), max_length=255)
    city = models.CharField(_("city"), max_length=100)
    country = models.CharField(_("country"), max_length=100)
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )
    venue_details = models.TextField(_("venue details"), blank=True)
    capacity = models.PositiveIntegerField(
        _("capacity"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("location")
        verbose_name_plural = _("locations")
    
    def __str__(self):
        return f"{self.name}, {self.city}"


class EventCategory(BaseModel):
    """Category model for events."""
    
    name = models.CharField(_("name"), max_length=100)
    slug = models.SlugField(_("slug"), unique=True)
    description = models.TextField(_("description"), blank=True)
    icon = models.ImageField(
        _("icon"),
        upload_to=get_upload_path,
        blank=True,
        null=True
    )
    
    class Meta:
        verbose_name = _("event category")
        verbose_name_plural = _("event categories")
    
    def __str__(self):
        return self.name


class Event(BaseModel):
    """Event model for creating and managing events."""
    
    STATUS_CHOICES = (
        ('draft', _('Draft')),
        ('published', _('Published')),
        ('canceled', _('Canceled')),
        ('finished', _('Finished')),
    )
    
    TYPE_CHOICES = (
        ('concert', _('Concert')),
        ('conference', _('Conference')),
        ('festival', _('Festival')),
        ('party', _('Party')),
        ('sport', _('Sport')),
        ('theater', _('Theater')),
        ('workshop', _('Workshop')),
        ('other', _('Other')),
    )
    
    title = models.CharField(_("title"), max_length=255)
    slug = models.SlugField(_("slug"), unique=True)
    description = models.TextField(_("description"))
    short_description = models.CharField(_("short description"), max_length=255)
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
        default='other'
    )
    start_date = models.DateTimeField(_("start date"))
    end_date = models.DateTimeField(_("end date"))
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name=_("location")
    )
    category = models.ForeignKey(
        EventCategory,
        on_delete=models.SET_NULL,
        related_name='events',
        verbose_name=_("category"),
        null=True,
        blank=True
    )
    featured = models.BooleanField(_("featured"), default=False)
    tags = models.CharField(_("tags"), max_length=255, blank=True)
    
    # Organizer info
    organizer = models.ForeignKey(
        'organizers.Organizer',
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name=_("organizer")
    )
    
    # Additional information
    age_restriction = models.CharField(
        _("age restriction"),
        max_length=50,
        blank=True
    )
    dresscode = models.CharField(_("dress code"), max_length=100, blank=True)
    accessibility = models.TextField(_("accessibility"), blank=True)
    parking = models.TextField(_("parking"), blank=True)
    
    # Sales configuration
    max_tickets_per_purchase = models.PositiveIntegerField(
        _("max tickets per purchase"),
        default=10
    )
    ticket_sales_start = models.DateTimeField(
        _("ticket sales start"),
        null=True,
        blank=True
    )
    ticket_sales_end = models.DateTimeField(
        _("ticket sales end"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("event")
        verbose_name_plural = _("events")
        ordering = ['-start_date']
    
    def __str__(self):
        return self.title
    
    @property
    def is_active(self):
        """Return True if the event is active."""
        return self.status == 'published'
    
    @property
    def is_past(self):
        """Return True if the event is in the past."""
        return self.end_date < timezone.now()
    
    @property
    def is_upcoming(self):
        """Return True if the event is upcoming."""
        return self.start_date > timezone.now() and self.status == 'published'
    
    @property
    def is_ongoing(self):
        """Return True if the event is ongoing."""
        now = timezone.now()
        return (
            self.start_date <= now and 
            self.end_date >= now and 
            self.status == 'published'
        )
    
    @property
    def tags_list(self):
        """Return a list of tags."""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(',')]


class EventImage(BaseModel):
    """Image model for events."""
    
    TYPE_CHOICES = (
        ('image', _('Image')),
        ('banner', _('Banner')),
        ('thumbnail', _('Thumbnail')),
        ('gallery', _('Gallery')),
    )
    
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name=_("event")
    )
    image = models.ImageField(
        _("image"),
        upload_to=get_upload_path
    )
    alt = models.CharField(_("alt text"), max_length=255, blank=True)
    type = models.CharField(
        _("type"),
        max_length=20,
        choices=TYPE_CHOICES,
        default='image'
    )
    order = models.PositiveIntegerField(_("order"), default=0)
    
    class Meta:
        verbose_name = _("event image")
        verbose_name_plural = _("event images")
        ordering = ['order']
    
    def __str__(self):
        return f"{self.event.title} - {self.get_type_display()}"


class TicketTier(BaseModel):
    """Ticket tier model for different ticket types in an event."""
    
    TYPE_CHOICES = (
        ('general', _('General')),
        ('vip', _('VIP')),
        ('early-bird', _('Early Bird')),
        ('group', _('Group')),
        ('student', _('Student')),
        ('child', _('Child')),
        ('senior', _('Senior')),
        ('other', _('Other')),
    )
    
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='ticket_tiers',
        verbose_name=_("event")
    )
    name = models.CharField(_("name"), max_length=100)
    type = models.CharField(
        _("type"),
        max_length=20,
        choices=TYPE_CHOICES,
        default='general'
    )
    description = models.TextField(_("description"), blank=True)
    price = models.DecimalField(_("price"), max_digits=10, decimal_places=2)
    service_fee = models.DecimalField(
        _("service fee"),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    capacity = models.PositiveIntegerField(_("capacity"))
    available = models.PositiveIntegerField(_("available"))
    is_public = models.BooleanField(_("is public"), default=True)
    max_per_order = models.PositiveIntegerField(
        _("max per order"),
        default=10
    )
    min_per_order = models.PositiveIntegerField(
        _("min per order"),
        default=1
    )
    benefits = models.TextField(_("benefits"), blank=True)
    
    # Discount options
    original_price = models.DecimalField(
        _("original price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    is_early_bird = models.BooleanField(_("is early bird"), default=False)
    early_bird_deadline = models.DateTimeField(
        _("early bird deadline"),
        null=True,
        blank=True
    )
    
    # Metadata
    is_highlighted = models.BooleanField(_("is highlighted"), default=False)
    is_waitlist = models.BooleanField(_("is waitlist"), default=False)
    category = models.CharField(_("category"), max_length=100, blank=True)
    category_description = models.CharField(
        _("category description"),
        max_length=255,
        blank=True
    )
    image = models.ImageField(
        _("image"),
        upload_to=get_upload_path,
        blank=True,
        null=True
    )
    
    class Meta:
        verbose_name = _("ticket tier")
        verbose_name_plural = _("ticket tiers")
        ordering = ['price']
    
    def __str__(self):
        return f"{self.event.title} - {self.name}"
    
    @property
    def benefits_list(self):
        """Return a list of benefits."""
        if not self.benefits:
            return []
        return [benefit.strip() for benefit in self.benefits.split('\n')]
    
    @property
    def total_price(self):
        """Return the total price including service fee."""
        return self.price + self.service_fee
    
    @property
    def discount_amount(self):
        """Return the discount amount if original price is set."""
        if not self.original_price:
            return 0
        return self.original_price - self.price
    
    @property
    def discount_percentage(self):
        """Return the discount percentage if original price is set."""
        if not self.original_price or self.original_price <= 0:
            return 0
        return int(100 - (self.price / self.original_price * 100))
    
    @property
    def is_sold_out(self):
        """Return True if the tier is sold out."""
        return self.available <= 0 