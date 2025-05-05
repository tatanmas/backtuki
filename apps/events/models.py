"""Models for the events app."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator
from django.utils import timezone
import uuid
import json

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
    
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('draft_complete', 'Borrador completo'),
        ('published', 'Publicado'),
        ('cancelled', 'Cancelado'),
        ('completed', 'Completado')
    ]
    
    TYPE_CHOICES = (
        ('conference', _('Conference')),
        ('concert', _('Concert')),
        ('sports', _('Sports')),
        ('theater', _('Theater')),
        ('workshop', _('Workshop')),
        ('festival', _('Festival')),
        ('party', _('Party')),
        ('other', _('Other')),
    )
    
    VISIBILITY_CHOICES = (
        ('public', _('Public')),
        ('private', _('Private')),
        ('password', _('Password Protected')),
    )
    
    EVENT_TEMPLATE_CHOICES = (
        ('standard', _('Standard')),
        ('multi_day', _('Multi-Day')),
        ('multi_session', _('Multi-Session')),
        ('seated', _('Seated')),
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
    visibility = models.CharField(
        _("visibility"),
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='public'
    )
    password = models.CharField(
        _("password"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("Password for private events")
    )
    type = models.CharField(
        _("type"),
        max_length=20,
        choices=TYPE_CHOICES,
        default='other'
    )
    template = models.CharField(
        _("template"),
        max_length=20,
        choices=EVENT_TEMPLATE_CHOICES,
        default='standard'
    )
    start_date = models.DateTimeField(_("start date"), null=True, blank=True)
    end_date = models.DateTimeField(_("end date"), null=True, blank=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name=_("location"),
        null=True,
        blank=True
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
    
    # Analytics
    views_count = models.PositiveIntegerField(_("views count"), default=0)
    cart_adds_count = models.PositiveIntegerField(_("cart adds count"), default=0)
    conversion_count = models.PositiveIntegerField(_("conversion count"), default=0)
    
    class Meta:
        verbose_name = _("event")
        verbose_name_plural = _("events")
        ordering = ['-start_date']
    
    def __str__(self):
        return self.title
    
    @property
    def is_active(self):
        """Return True if the event is active."""
        return self.status == 'active'
    
    @property
    def is_past(self):
        """Return True if the event is in the past."""
        return self.end_date < timezone.now()
    
    @property
    def is_upcoming(self):
        """Return True if the event is upcoming."""
        return self.start_date > timezone.now() and self.status == 'active'
    
    @property
    def is_ongoing(self):
        """Return True if the event is ongoing."""
        now = timezone.now()
        return (
            self.start_date <= now and 
            self.end_date >= now and 
            self.status == 'active'
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


class TicketCategory(BaseModel):
    """Category model for grouping tickets."""
    
    STATUS_CHOICES = (
        ('active', _('Active')),
        ('hidden', _('Hidden')),
        ('sold_out', _('Sold Out')),
    )
    
    VISIBILITY_CHOICES = (
        ('public', _('Public')),
        ('private', _('Private')),
        ('password', _('Password Protected')),
    )
    
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='ticket_categories',
        verbose_name=_("event")
    )
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    capacity = models.PositiveIntegerField(_("capacity"), default=0)
    sold = models.PositiveIntegerField(_("sold"), default=0)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    visibility = models.CharField(
        _("visibility"),
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='public'
    )
    color = models.CharField(
        _("color"),
        max_length=20,
        default='#3b82f6'
    )
    order = models.PositiveIntegerField(_("order"), default=0)
    
    # Access control
    max_per_purchase = models.PositiveIntegerField(
        _("max per purchase"),
        default=10
    )
    min_per_purchase = models.PositiveIntegerField(
        _("min per purchase"),
        default=1
    )
    
    # Sale period
    sale_start_date = models.DateField(
        _("sale start date"),
        null=True,
        blank=True
    )
    sale_end_date = models.DateField(
        _("sale end date"),
        null=True,
        blank=True
    )
    sale_start_time = models.TimeField(
        _("sale start time"),
        null=True,
        blank=True
    )
    sale_end_time = models.TimeField(
        _("sale end time"),
        null=True,
        blank=True
    )
    
    # Access period (when tickets are valid)
    access_start_date = models.DateField(
        _("access start date"),
        null=True,
        blank=True
    )
    access_end_date = models.DateField(
        _("access end date"),
        null=True,
        blank=True
    )
    access_start_time = models.TimeField(
        _("access start time"),
        null=True,
        blank=True
    )
    access_end_time = models.TimeField(
        _("access end time"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("ticket category")
        verbose_name_plural = _("ticket categories")
        ordering = ['order']
    
    def __str__(self):
        return f"{self.name} - {self.event.title}"
    
    @property
    def available(self):
        """Return number of available tickets."""
        return max(0, self.capacity - self.sold)
    
    @property
    def is_sold_out(self):
        """Return True if category is sold out."""
        return self.available == 0 or self.status == 'sold_out'


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
    )
    
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='ticket_tiers',
        verbose_name=_("event")
    )
    category = models.ForeignKey(
        TicketCategory,
        on_delete=models.SET_NULL,
        related_name='ticket_tiers',
        verbose_name=_("category"),
        null=True,
        blank=True
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
    order = models.PositiveIntegerField(_("order"), default=0)
    image = models.ImageField(
        _("image"),
        upload_to=get_upload_path,
        blank=True,
        null=True
    )
    
    # Link to form for collecting attendee information
    form = models.ForeignKey(
        'EventForm',
        on_delete=models.SET_NULL,
        related_name='ticket_tiers',
        verbose_name=_("form"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("ticket tier")
        verbose_name_plural = _("ticket tiers")
        ordering = ['order', 'price']
    
    def __str__(self):
        return f"{self.name} - {self.event.title}"
    
    @property
    def benefits_list(self):
        """Return a list of benefits."""
        if not self.benefits:
            return []
        return [benefit.strip() for benefit in self.benefits.split(',')]
    
    @property
    def total_price(self):
        """Return total price including service fee."""
        return self.price + self.service_fee
    
    @property
    def discount_amount(self):
        """Return discount amount if original price is set."""
        if not self.original_price:
            return 0
        return max(0, self.original_price - self.price)
    
    @property
    def discount_percentage(self):
        """Return discount percentage if original price is set."""
        if not self.original_price or self.original_price <= 0:
            return 0
        return int((self.discount_amount / self.original_price) * 100)
    
    @property
    def is_sold_out(self):
        """Return True if ticket is sold out."""
        return self.available <= 0


class EventForm(BaseModel):
    """Form model for collecting attendee information."""
    
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    organizer = models.ForeignKey(
        'organizers.Organizer',
        on_delete=models.CASCADE,
        related_name='forms',
        verbose_name=_("organizer")
    )
    is_default = models.BooleanField(_("is default"), default=False)
    
    class Meta:
        verbose_name = _("event form")
        verbose_name_plural = _("event forms")
    
    def __str__(self):
        return self.name


class FormField(BaseModel):
    """Field model for event forms."""
    
    TYPE_CHOICES = (
        ('text', _('Text')),
        ('email', _('Email')),
        ('number', _('Number')),
        ('select', _('Select')),
        ('checkbox', _('Checkbox')),
        ('radio', _('Radio')),
        ('date', _('Date')),
        ('time', _('Time')),
        ('phone', _('Phone')),
        ('textarea', _('Textarea')),
        ('heading', _('Heading')),
        ('paragraph', _('Paragraph')),
    )
    
    WIDTH_CHOICES = (
        ('full', _('Full width')),
        ('half', _('Half width')),
        ('third', _('Third width')),
    )
    
    form = models.ForeignKey(
        EventForm,
        on_delete=models.CASCADE,
        related_name='fields',
        verbose_name=_("form")
    )
    label = models.CharField(_("label"), max_length=100)
    type = models.CharField(
        _("type"),
        max_length=20,
        choices=TYPE_CHOICES,
        default='text'
    )
    required = models.BooleanField(_("required"), default=False)
    placeholder = models.CharField(
        _("placeholder"),
        max_length=100,
        blank=True
    )
    help_text = models.CharField(
        _("help text"),
        max_length=255,
        blank=True
    )
    default_value = models.CharField(
        _("default value"),
        max_length=255,
        blank=True
    )
    order = models.PositiveIntegerField(_("order"), default=0)
    options = models.TextField(
        _("options"),
        blank=True,
        help_text=_("Comma-separated options for select, checkbox, radio")
    )
    width = models.CharField(
        _("width"),
        max_length=20,
        choices=WIDTH_CHOICES,
        default='full'
    )
    validations = models.JSONField(
        _("validations"),
        default=dict,
        blank=True,
        help_text=_("Validations like min, max, minLength, maxLength, pattern")
    )
    conditional_display = models.JSONField(
        _("conditional display"),
        default=list,
        blank=True,
        help_text=_("Rules for conditional display based on other fields")
    )
    
    class Meta:
        verbose_name = _("form field")
        verbose_name_plural = _("form fields")
        ordering = ['order']
    
    def __str__(self):
        return f"{self.label} - {self.form.name}"
    
    @property
    def options_list(self):
        """Return a list of options."""
        if not self.options:
            return []
        return [option.strip() for option in self.options.split(',')]


def generate_order_number():
    """Generate a unique order number."""
    return f"ORD-{str(uuid.uuid4())[:8].upper()}"


class Order(BaseModel):
    """Order model for ticket purchases."""
    
    STATUS_CHOICES = (
        ('pending', _('Pending')),
        ('paid', _('Paid')),
        ('cancelled', _('Cancelled')),
        ('refunded', _('Refunded')),
        ('failed', _('Failed')),
    )
    
    order_number = models.CharField(
        _("order number"),
        max_length=50,
        unique=True,
        default=generate_order_number
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='orders',
        verbose_name=_("user"),
        null=True,
        blank=True
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name=_("event")
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    email = models.EmailField(_("email"))
    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    subtotal = models.DecimalField(
        _("subtotal"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    taxes = models.DecimalField(
        _("taxes"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    service_fee = models.DecimalField(
        _("service fee"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    total = models.DecimalField(
        _("total"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    payment_method = models.CharField(_("payment method"), max_length=50, blank=True)
    payment_id = models.CharField(_("payment id"), max_length=100, blank=True)
    coupon = models.ForeignKey(
        'Coupon',
        on_delete=models.SET_NULL,
        related_name='orders',
        verbose_name=_("coupon"),
        null=True,
        blank=True
    )
    discount = models.DecimalField(
        _("discount"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    notes = models.TextField(_("notes"), blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.TextField(_("user agent"), blank=True)
    refund_reason = models.TextField(_("refund reason"), blank=True)
    refunded_amount = models.DecimalField(
        _("refunded amount"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    
    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ['-created_at']
    
    def __str__(self):
        return self.order_number
    
    @property
    def buyer_name(self):
        """Return the buyer's full name."""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_paid(self):
        """Return True if order is paid."""
        return self.status == 'paid'
    
    @property
    def is_pending(self):
        """Return True if order is pending."""
        return self.status == 'pending'
    
    @property
    def is_cancelled(self):
        """Return True if order is cancelled."""
        return self.status == 'cancelled'
    
    @property
    def is_refunded(self):
        """Return True if order is refunded."""
        return self.status == 'refunded'
    
    @property
    def is_failed(self):
        """Return True if order failed."""
        return self.status == 'failed'


class OrderItem(BaseModel):
    """Order item model for individual tickets in an order."""
    
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_("order")
    )
    ticket_tier = models.ForeignKey(
        TicketTier,
        on_delete=models.PROTECT,
        related_name='order_items',
        verbose_name=_("ticket tier")
    )
    quantity = models.PositiveIntegerField(_("quantity"))
    unit_price = models.DecimalField(
        _("unit price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    unit_service_fee = models.DecimalField(
        _("unit service fee"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    subtotal = models.DecimalField(
        _("subtotal"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    
    class Meta:
        verbose_name = _("order item")
        verbose_name_plural = _("order items")
    
    def __str__(self):
        return f"{self.ticket_tier.name} - {self.order.order_number}"
    
    def save(self, *args, **kwargs):
        """Calculate subtotal before saving."""
        self.subtotal = (self.unit_price + self.unit_service_fee) * self.quantity
        super().save(*args, **kwargs)


def generate_ticket_number():
    """Generate a unique ticket number."""
    return f"TIX-{str(uuid.uuid4())[:8].upper()}"


class Ticket(BaseModel):
    """Ticket model for individual attendees."""
    
    STATUS_CHOICES = (
        ('active', _('Active')),
        ('used', _('Used')),
        ('cancelled', _('Cancelled')),
        ('refunded', _('Refunded')),
    )
    
    ticket_number = models.CharField(
        _("ticket number"),
        max_length=50,
        unique=True,
        default=generate_ticket_number
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name='tickets',
        verbose_name=_("order item")
    )
    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email"))
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    checked_in = models.BooleanField(_("checked in"), default=False)
    check_in_time = models.DateTimeField(
        _("check in time"),
        null=True,
        blank=True
    )
    form_data = models.JSONField(
        _("form data"),
        default=dict,
        blank=True,
        help_text=_("Form data collected for this ticket")
    )
    
    class Meta:
        verbose_name = _("ticket")
        verbose_name_plural = _("tickets")
    
    def __str__(self):
        return self.ticket_number
    
    @property
    def attendee_name(self):
        """Return the attendee's full name."""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def event(self):
        """Return the related event."""
        return self.order_item.ticket_tier.event
    
    @property
    def ticket_tier(self):
        """Return the related ticket tier."""
        return self.order_item.ticket_tier
    
    @property
    def is_active(self):
        """Return True if ticket is active."""
        return self.status == 'active'
    
    @property
    def is_used(self):
        """Return True if ticket is used."""
        return self.status == 'used' or self.checked_in


class Coupon(BaseModel):
    """Coupon model for discounts."""
    
    TYPE_CHOICES = (
        ('percentage', _('Percentage')),
        ('fixed', _('Fixed Amount')),
    )
    
    STATUS_CHOICES = (
        ('active', _('Active')),
        ('expired', _('Expired')),
        ('used', _('Used')),
        ('inactive', _('Inactive')),
    )
    
    code = models.CharField(_("code"), max_length=50, unique=True)
    description = models.TextField(_("description"), blank=True)
    organizer = models.ForeignKey(
        'organizers.Organizer',
        on_delete=models.CASCADE,
        related_name='coupons',
        verbose_name=_("organizer")
    )
    # Single event reference (legacy)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='coupons',
        verbose_name=_("event"),
        null=True,
        blank=True,
        help_text=_("Legacy field. If null, coupon applies to all events or specified in events_list")
    )
    # Multiple events support as JSON array of event IDs
    events_list = models.JSONField(
        _("applicable events"),
        null=True,
        blank=True,
        help_text=_("List of event IDs this coupon applies to. Null means all events.")
    )
    discount_type = models.CharField(
        _("discount type"),
        max_length=20,
        choices=TYPE_CHOICES,
        default='percentage'
    )
    discount_value = models.DecimalField(
        _("discount value"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    min_purchase = models.DecimalField(
        _("minimum purchase"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0
    )
    max_discount = models.DecimalField(
        _("maximum discount"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True
    )
    start_date = models.DateTimeField(_("start date"), null=True, blank=True)
    end_date = models.DateTimeField(_("end date"), null=True, blank=True)
    start_time = models.TimeField(_("start time"), null=True, blank=True)
    end_time = models.TimeField(_("end time"), null=True, blank=True)
    usage_limit = models.PositiveIntegerField(
        _("usage limit"),
        null=True,
        blank=True
    )
    usage_count = models.PositiveIntegerField(_("usage count"), default=0)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    is_active = models.BooleanField(_("is active"), default=True)
    ticket_tiers = models.ManyToManyField(
        TicketTier,
        related_name='coupons',
        verbose_name=_("applicable ticket tiers"),
        blank=True
    )
    ticket_categories = models.ManyToManyField(
        TicketCategory,
        related_name='coupons',
        verbose_name=_("applicable ticket categories"),
        blank=True
    )
    
    class Meta:
        verbose_name = _("coupon")
        verbose_name_plural = _("coupons")
    
    def __str__(self):
        return self.code
    
    @property
    def is_active_property(self):
        """Return True if coupon is active."""
        if self.status != 'active' or not self.is_active:
            return False
        
        now = timezone.now()
        
        if self.start_date and now < self.start_date:
            return False
        
        if self.end_date and now > self.end_date:
            return False
        
        if self.usage_limit and self.usage_count >= self.usage_limit:
            return False
        
        return True
    
    def apply_to_multiple_events(self, event_ids):
        """Helper method to set multiple events for this coupon."""
        self.events_list = event_ids
        self.save()
    
    def get_applicable_events(self):
        """
        Get list of applicable event IDs.
        Returns None if applicable to all events, otherwise returns list of IDs.
        """
        # If using the new events_list field
        if self.events_list is not None:
            return self.events_list
        
        # Legacy fallback
        if self.event is not None:
            return [str(self.event.id)]
        
        # Applies to all events
        return None


class EventCommunication(BaseModel):
    """Communication model for email templates and scheduled communications."""
    
    TYPE_CHOICES = (
        ('confirmation', _('Order Confirmation')),
        ('reminder', _('Event Reminder')),
        ('update', _('Event Update')),
        ('cancellation', _('Event Cancellation')),
        ('thank_you', _('Thank You')),
        ('custom', _('Custom')),
    )
    
    STATUS_CHOICES = (
        ('draft', _('Draft')),
        ('scheduled', _('Scheduled')),
        ('sent', _('Sent')),
        ('failed', _('Failed')),
    )
    
    name = models.CharField(_("name"), max_length=100)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='communications',
        verbose_name=_("event")
    )
    type = models.CharField(
        _("type"),
        max_length=20,
        choices=TYPE_CHOICES,
        default='custom'
    )
    subject = models.CharField(_("subject"), max_length=255)
    content = models.TextField(_("content"))
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    scheduled_date = models.DateTimeField(
        _("scheduled date"),
        null=True,
        blank=True
    )
    sent_date = models.DateTimeField(
        _("sent date"),
        null=True,
        blank=True
    )
    recipients_count = models.PositiveIntegerField(
        _("recipients count"),
        default=0
    )
    delivery_count = models.PositiveIntegerField(
        _("delivery count"),
        default=0
    )
    open_count = models.PositiveIntegerField(
        _("open count"),
        default=0
    )
    click_count = models.PositiveIntegerField(
        _("click count"),
        default=0
    )
    
    class Meta:
        verbose_name = _("event communication")
        verbose_name_plural = _("event communications")
    
    def __str__(self):
        return f"{self.name} - {self.event.title}" 