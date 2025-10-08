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
    """Location model for events - supports both physical and virtual locations."""
    
    name = models.CharField(_("name"), max_length=255, help_text=_("Name of the venue or platform"))
    address = models.TextField(_("address"), help_text=_("Physical address or virtual meeting URL"))
    
    class Meta:
        verbose_name = _("location")
        verbose_name_plural = _("locations")
    
    def __str__(self):
        return self.name
    
    @property
    def is_virtual(self):
        """Return True if this is a virtual location (URL)."""
        return self.address and (
            self.address.startswith('http://') or 
            self.address.startswith('https://') or
            'zoom.us' in self.address.lower() or
            'meet.google.com' in self.address.lower() or
            'teams.microsoft.com' in self.address.lower()
        )


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
    
    PRICING_MODE_CHOICES = (
        ('simple', _('Simple - Free with basic settings')),
        ('complex', _('Complex - Paid with tickets/categories')),
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
    
    # Pricing mode - determines if event uses simple or complex ticket system
    pricing_mode = models.CharField(
        _("pricing mode"),
        max_length=20,
        choices=PRICING_MODE_CHOICES,
        default='simple',
        help_text=_("Simple: free events with basic settings. Complex: paid events with tickets/categories.")
    )
    
    # Simple event settings (only used when pricing_mode='simple')
    is_free = models.BooleanField(
        _("is free"),
        default=True,
        help_text=_("Whether this event is free (only for simple pricing mode)")
    )
    requires_approval = models.BooleanField(
        _("requires approval"),
        default=False,
        help_text=_("Whether attendees need approval to join (only for simple pricing mode)")
    )
    simple_capacity = models.PositiveIntegerField(
        _("simple capacity"),
        null=True,
        blank=True,
        help_text=_("Total capacity for simple events (null = unlimited)")
    )
    simple_price = models.DecimalField(
        _("simple price"),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_("Price for simple paid events")
    )
    
    # ✅ NUEVO CAMPO PARA EVENTOS PÚBLICOS
    requires_email_validation = models.BooleanField(
        _("requires email validation"),
        default=False,
        help_text=_("Si el evento requiere validación de email para publicarse")
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
    
    # Soft delete
    deleted_at = models.DateTimeField(
        _("deleted at"),
        null=True,
        blank=True,
        help_text=_("When the event was soft deleted")
    )
    
    class Meta:
        verbose_name = _("event")
        verbose_name_plural = _("events")
        ordering = ['-start_date']
    
    def __str__(self):
        return self.title
    
    
    @property
    def is_past(self):
        """Return True if the event is in the past."""
        if not self.end_date:
            return False
        return self.end_date < timezone.now()
    
    @property
    def is_upcoming(self):
        """Return True if the event is upcoming and available for sales."""
        if not self.start_date:
            return False
        now = timezone.now()
        return (
            self.start_date > now and 
            self.status == 'published' and
            self.is_sales_active
        )
    
    @property
    def is_ongoing(self):
        """Return True if the event is currently happening."""
        if not self.start_date or not self.end_date:
            return False
        now = timezone.now()
        return (
            self.start_date <= now and 
            self.end_date >= now and 
            self.status == 'published'
        )
    
    @property
    def is_sales_active(self):
        """🚀 ENTERPRISE: Return True if ticket sales are currently active for this event."""
        now = timezone.now()
        
        # Check if event is in correct status for sales
        if self.status != 'published':
            return False
            
        # Check sales window
        if self.ticket_sales_start and now < self.ticket_sales_start:
            return False
            
        if self.ticket_sales_end and now > self.ticket_sales_end:
            return False
            
        # Check if event hasn't passed
        if self.is_past:
            return False
            
        return True
    
    @property
    def is_available_for_purchase(self):
        """
        🚀 ENTERPRISE: Return True if event is available for ticket purchase.
        This is the main method for frontend filtering.
        """
        return (
            self.is_sales_active and
            self.visibility == 'public' and
            self.has_available_tickets
        )
    
    @property
    def has_available_tickets(self):
        """🚀 ENTERPRISE: Check if event has available tickets for purchase."""
        if self.pricing_mode == 'simple':
            if self.simple_capacity is None:
                return True  # Unlimited capacity
            return self.simple_available_capacity > 0
        
        # For complex events, check ticket tiers
        return self.ticket_tiers.filter(
            is_public=True,
            available__gt=0
        ).exists()

    @property
    def tags_list(self):
        """Return a list of tags."""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(',')]
    
    @property
    def is_simple_event(self):
        """Return True if this is a simple event (free with basic settings)."""
        return self.pricing_mode == 'simple'
    
    @property
    def is_complex_event(self):
        """Return True if this is a complex event (with tickets/categories)."""
        return self.pricing_mode == 'complex'
    
    @property
    def simple_available_capacity(self):
        """Return available capacity for simple events."""
        if not self.is_simple_event or self.simple_capacity is None:
            return None  # Unlimited
        
        # Count confirmed attendees for simple events
        from apps.bookings.models import SimpleBooking
        confirmed_count = SimpleBooking.objects.filter(
            event=self,
            status='confirmed'
        ).count()
        
        return max(0, self.simple_capacity - confirmed_count)
    
    def clean(self):
        """Validate event data based on pricing mode."""
        from django.core.exceptions import ValidationError
        
        if self.pricing_mode == 'simple':
            # Simple events must be free or have a simple price
            if not self.is_free and not self.simple_price:
                raise ValidationError("Simple paid events must have a simple_price set.")
        
        elif self.pricing_mode == 'complex':
            # Complex events should not use simple event fields
            if self.is_free:
                raise ValidationError("Complex events cannot use is_free flag. Use ticket pricing instead.")
        
        super().clean()
    
    @property
    def is_deleted(self):
        """Return True if event is soft deleted."""
        return self.deleted_at is not None
    
    @property
    def total_revenue(self):
        """Calculate total revenue from paid orders."""
        from django.db.models import Sum
        return self.orders.filter(status='paid').aggregate(
            total=Sum('total')
        )['total'] or 0
    
    def can_be_deleted(self):
        """Check if event can be soft deleted (no revenue)."""
        return self.total_revenue == 0
    
    def soft_delete(self):
        """Perform soft delete if allowed."""
        if not self.can_be_deleted():
            raise ValueError("No se puede eliminar un evento que tiene ingresos")
        
        from django.utils import timezone
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])
    
    def restore(self):
        """Restore soft deleted event."""
        self.deleted_at = None
        self.save(update_fields=['deleted_at'])


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
    capacity = models.PositiveIntegerField(_("capacity"), default=0, null=True, blank=True, 
                                          help_text=_("Leave empty for unlimited capacity"))
    # 🚀 ENTERPRISE: Removed sold field - now calculated dynamically via property
    # sold = models.PositiveIntegerField(_("sold"), default=0)  # ❌ DEPRECATED: Never updated
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
    
    # Approval workflow
    requires_approval = models.BooleanField(
        _("requires approval"),
        default=False,
        help_text=_("Whether tickets in this category require organizer approval before purchase/access")
    )
    
    class Meta:
        verbose_name = _("ticket category")
        verbose_name_plural = _("ticket categories")
        ordering = ['order']
    
    def __str__(self):
        return f"{self.name} - {self.event.title}"
    
    @property 
    def sold(self):
        """🚀 ENTERPRISE: Return number of tickets sold in this category (calculated dynamically)."""
        # Sum tickets sold across all tiers in this category
        total_sold = 0
        for tier in self.ticket_tiers.all():
            total_sold += tier.tickets_sold
        return total_sold
    
    @property
    def available(self):
        """Return number of available tickets."""
        # If capacity is null/None, return a large number to indicate unlimited capacity
        if self.capacity is None:
            return 9999999
        return max(0, self.capacity - self.sold)
    
    @property
    def is_sold_out(self):
        """Return True if category is sold out."""
        # If capacity is unlimited (None), category is never sold out
        if self.capacity is None:
            return False
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
    capacity = models.PositiveIntegerField(_("capacity"), null=True, blank=True, help_text=_("Leave empty for unlimited capacity"))
    available = models.PositiveIntegerField(_("available"), null=True, blank=True, help_text=_("Leave empty for unlimited availability"))  # 🚀 ENTERPRISE: Allow null for unlimited
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
        'forms.Form',
        on_delete=models.SET_NULL,
        related_name='ticket_tiers',
        verbose_name=_("form"),
        null=True,
        blank=True
    )
    
    # Approval workflow
    requires_approval = models.BooleanField(
        _("requires approval"),
        default=False,
        help_text=_("Whether this ticket type requires organizer approval before purchase/access")
    )
    
    class Meta:
        verbose_name = _("ticket tier")
        verbose_name_plural = _("ticket tiers")
        ordering = ['order', 'price']
        
        # 🚀 ENTERPRISE: Database constraints for data integrity
        constraints = [
            models.CheckConstraint(
                check=models.Q(available__gte=0),
                name='%(app_label)s_%(class)s_available_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(capacity__gte=0),
                name='%(app_label)s_%(class)s_capacity_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(max_per_order__gte=1),
                name='%(app_label)s_%(class)s_max_per_order_positive'
            ),
            models.CheckConstraint(
                check=models.Q(min_per_order__gte=1),
                name='%(app_label)s_%(class)s_min_per_order_positive'
            ),
            models.CheckConstraint(
                check=models.Q(max_per_order__gte=models.F('min_per_order')),
                name='%(app_label)s_%(class)s_max_gte_min_per_order'
            ),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.event.title}"
    
    def save(self, *args, **kwargs):
        """🚀 ENTERPRISE: Auto-initialize available if not set."""
        # If this is a new instance and available is still default (0), set it to capacity
        if not self.pk and self.available == 0:
            if self.capacity is not None:
                # Limited capacity: set available to capacity
                self.available = self.capacity
            else:
                # Unlimited capacity: set available to a large number
                self.available = 9999999
        super().save(*args, **kwargs)
    
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
    
    def get_tickets_on_hold(self):
        """🚀 ENTERPRISE: Return number of tickets currently on hold (use this in views).""" 
        from django.utils import timezone
        return self.holds.filter(
            released=False,
            expires_at__gt=timezone.now()
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
    
    @property
    def tickets_on_hold(self):
        """🚀 ENTERPRISE: Return number of tickets currently on hold (cached property)."""
        # ⚠️ WARNING: This property makes a database query every time it's accessed
        # For better performance in views, use:
        # - .prefetch_related('holds') in QuerySet
        # - Or call .get_tickets_on_hold() method directly
        return self.get_tickets_on_hold()
    
    @property
    def real_available(self):
        """🚀 ENTERPRISE: Return tickets available for immediate purchase (excluding holds)."""
        if self.available is None:
            return None  # Unlimited capacity
        return max(0, self.available - self.tickets_on_hold)
    
    @property
    def tickets_sold(self):
        """🚀 ENTERPRISE: Return number of tickets actually sold (paid orders)."""
        return self.order_items.filter(
            order__status='paid'
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
    

    
    def can_reserve(self, quantity):
        """
        🚀 ENTERPRISE: Check if we can reserve the requested quantity.
        Takes into account current holds and available stock.
        """
        return self.real_available >= quantity
    
    def get_availability_summary(self):
        """🚀 ENTERPRISE: Get complete availability summary for transparency."""
        # 🛡️ ENTERPRISE: Safe calculation handling None values
        sold = self.tickets_sold or 0
        capacity = self.capacity
        
        # Calculate utilization rate safely
        if capacity and capacity > 0 and sold >= 0:
            utilization_rate = (sold / capacity * 100)
        else:
            utilization_rate = 0
            
        return {
            'total_capacity': capacity,
            'available': self.available,
            'sold': sold,
            'on_hold': self.tickets_on_hold,
            'real_available': self.real_available,
            'utilization_rate': round(utilization_rate, 2)  # Round to 2 decimals for cleaner output
        }





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
    
    # 🚀 ENTERPRISE: Enhanced check-in status to match frontend requirements
    CHECK_IN_STATUS_CHOICES = (
        ('pending', _('Pending')),           # Not checked in yet
        ('checked_in', _('Checked In')),     # Successfully checked in
        ('no_show', _('No Show')),           # Marked as no-show
    )
    
    # 🚀 ENTERPRISE: Approval status for tickets requiring approval
    APPROVAL_STATUS_CHOICES = (
        ('pending_approval', _('Pending Approval')),
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
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
    
    # 🚀 ENTERPRISE: Enhanced check-in system
    check_in_status = models.CharField(
        _("check-in status"),
        max_length=20,
        choices=CHECK_IN_STATUS_CHOICES,
        default='pending',
        help_text=_("Current check-in status of the ticket")
    )
    check_in_time = models.DateTimeField(
        _("check in time"),
        null=True,
        blank=True
    )
    check_in_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='checked_in_tickets',
        verbose_name=_("checked in by"),
        null=True,
        blank=True,
        help_text=_("User (guard/staff) who performed the check-in")
    )
    
    # 🚀 ENTERPRISE: Approval workflow for tickets requiring approval
    approval_status = models.CharField(
        _("approval status"),
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        null=True,
        blank=True,
        help_text=_("Approval status for tickets that require approval")
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='approved_tickets',
        verbose_name=_("approved by"),
        null=True,
        blank=True,
        help_text=_("User who approved/rejected this ticket")
    )
    approved_at = models.DateTimeField(
        _("approved at"),
        null=True,
        blank=True
    )
    rejection_reason = models.TextField(
        _("rejection reason"),
        blank=True,
        help_text=_("Reason for rejection if ticket was rejected")
    )
    
    # Legacy field for backward compatibility
    checked_in = models.BooleanField(
        _("checked in (legacy)"), 
        default=False,
        help_text=_("Legacy field. Use check_in_status instead.")
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


class TicketNote(BaseModel):
    """Model for internal notes on tickets."""
    
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='notes',
        verbose_name=_("ticket")
    )
    content = models.TextField(_("content"))
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("author")
    )
    is_internal = models.BooleanField(
        _("is internal"),
        default=True,
        help_text=_("Whether this note is internal (not visible to customer)")
    )
    
    class Meta:
        verbose_name = _("ticket note")
        verbose_name_plural = _("ticket notes")
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note on {self.ticket.ticket_number} by {self.author.username if self.author else 'System'}"



    
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
        return self.status == 'used' or self.check_in_status == 'checked_in'
    
    @property
    def requires_approval(self):
        """Return True if this ticket requires approval."""
        return self.order_item.ticket_tier.requires_approval
    
    @property
    def ticket_type(self):
        """Return the ticket tier name."""
        return self.order_item.ticket_tier.name
    
    @property
    def ticket_category(self):
        """Return the ticket category name."""
        category = self.order_item.ticket_tier.category
        return category.name if category else "Sin categoría"
    
    @property
    def order_number(self):
        """Return the order number."""
        return self.order_item.order.order_number
    
    @property
    def purchase_date(self):
        """Return the purchase date."""
        return self.order_item.order.created_at
    
    @property
    def ticket_price(self):
        """Return the ticket price."""
        return self.order_item.unit_price
    
    @property
    def phone(self):
        """Return the customer phone."""
        return self.order_item.order.phone


class TicketHold(BaseModel):
    """Temporary hold to reserve tickets and prevent overselling during checkout."""
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='ticket_holds',
        verbose_name=_("event")
    )
    ticket_tier = models.ForeignKey(
        TicketTier,
        on_delete=models.CASCADE,
        related_name='holds',
        verbose_name=_("ticket tier")
    )
    order = models.ForeignKey(
        'Order',
        on_delete=models.CASCADE,
        related_name='holds',
        verbose_name=_("order"),
        null=True,
        blank=True
    )
    quantity = models.PositiveIntegerField(_("quantity"))
    expires_at = models.DateTimeField(_("expires at"))
    released = models.BooleanField(_("released"), default=False)

    class Meta:
        verbose_name = _("ticket hold")
        verbose_name_plural = _("ticket holds")
        indexes = [
            models.Index(fields=["ticket_tier", "expires_at", "released"]),
            models.Index(fields=["event", "expires_at", "released"]),
        ]
        
        # 🚀 ENTERPRISE: Database constraints for data integrity
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gte=1),
                name='%(app_label)s_%(class)s_quantity_positive'
            ),
            models.CheckConstraint(
                check=models.Q(expires_at__gt=models.F('created_at')),
                name='%(app_label)s_%(class)s_expires_after_creation'
            ),
        ]

    def __str__(self):
        return f"HOLD-{self.ticket_tier_id}-{self.quantity}@{self.expires_at.isoformat()}"

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    def release(self):
        """🚀 ENTERPRISE: Release the hold and return tickets to availability (idempotent)."""
        if self.released:
            return
            
        from django.db import transaction
        from django.db.models import F
        
        # 🛡️ ENTERPRISE: Atomic operation to prevent race conditions
        with transaction.atomic():
            # Double-check pattern: verify again within transaction
            if self.released:
                return
                
            # 🚀 ATOMIC UPDATE: Use F() expression for safe concurrent updates
            # This ensures the database handles the addition atomically
            TicketTier.objects.filter(id=self.ticket_tier_id).update(
                available=F('available') + self.quantity
            )
            
            # Mark as released
            self.released = True
            self.save()


class CouponHold(BaseModel):
    """
    🚀 ENTERPRISE: Temporary hold to reserve coupon usage during checkout.
    
    Similar to TicketHold but for coupons. Prevents race conditions and 
    double usage during concurrent checkout processes.
    """
    coupon = models.ForeignKey(
        'Coupon',
        on_delete=models.CASCADE,
        related_name='holds',
        verbose_name=_("coupon")
    )
    order = models.ForeignKey(
        'Order',
        on_delete=models.CASCADE,
        related_name='coupon_holds',
        verbose_name=_("order"),
        null=True,
        blank=True
    )
    expires_at = models.DateTimeField(_("expires at"))
    released = models.BooleanField(_("released"), default=False)
    confirmed = models.BooleanField(_("confirmed"), default=False)
    
    class Meta:
        verbose_name = _("coupon hold")
        verbose_name_plural = _("coupon holds")
        indexes = [
            models.Index(fields=["coupon", "expires_at", "released"]),
            models.Index(fields=["order", "expires_at", "released"]),
        ]
        
        # 🚀 ENTERPRISE: Database constraints for data integrity
        constraints = [
            models.CheckConstraint(
                check=models.Q(expires_at__gt=models.F('created_at')),
                name='%(app_label)s_%(class)s_expires_after_creation'
            ),
        ]

    def __str__(self):
        return f"COUPON-HOLD-{self.coupon.code}-{self.order_id}@{self.expires_at.isoformat()}"

    @property
    def is_expired(self):
        """Check if hold has expired."""
        return self.expires_at <= timezone.now()

    def release(self):
        """🚀 ENTERPRISE: Release the coupon hold (idempotent)."""
        if not self.released:
            self.released = True
            self.save(update_fields=['released'])

    def confirm(self):
        """🚀 ENTERPRISE: Confirm the coupon hold and increment usage."""
        if self.released:
            raise ValueError("Cannot confirm released hold")
        
        if self.is_expired:
            raise ValueError("Cannot confirm expired hold")
        
        # Increment coupon usage atomically
        self.coupon.increment_usage()
        
        # Mark as confirmed
        self.confirmed = True
        self.save(update_fields=['confirmed'])


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
    description = models.TextField(_("description"), blank=True, null=True)
    organizer = models.ForeignKey(
        'organizers.Organizer',
        on_delete=models.CASCADE,
        related_name='coupons',
        verbose_name=_("organizer")
    )
    # 🚀 ENTERPRISE: Simplified Global vs Local coupon system
    # events_list = null -> GLOBAL (applies to all events)
    # events_list = [event_id] -> LOCAL (applies to specific event)
    events_list = models.JSONField(
        _("applicable events"),
        null=True,
        blank=True,
        help_text=_("null = Global (all events), [event_id] = Local (specific event)")
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
        null=True,
        blank=True,
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
    # 🚀 ENTERPRISE: start_time and end_time fields removed in migration 0023
    # Use start_date and end_date (DateTimeField) for temporal constraints
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
    
    # 🚀 ENTERPRISE: Helper methods for Global vs Local functionality
    @property
    def is_global(self) -> bool:
        """Return True if coupon is global (applies to all events)."""
        return self.events_list is None
    
    @property
    def is_local(self) -> bool:
        """Return True if coupon is local (applies to specific event)."""
        return self.events_list is not None and len(self.events_list) > 0
    
    @property
    def applicable_event_id(self) -> str | None:
        """Return the event ID this coupon applies to (for local coupons)."""
        if self.is_local and self.events_list:
            return self.events_list[0]  # Local coupons have only one event
        return None
    
    def get_applicable_events(self) -> list[str] | None:
        """Return list of applicable event IDs or None for global."""
        return self.events_list
    
    def __str__(self):
        scope = "🌍 GLOBAL" if self.is_global else "🎯 LOCAL"
        return f"{self.code} ({scope}) - {self.get_discount_type_display()}"
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
    
    @property
    def is_currently_valid(self):
        """🚀 ENTERPRISE: Return True if coupon is currently valid for use."""
        return self.is_active_property
    
    def get_analytics_data(self):
        """🚀 ENTERPRISE: Return comprehensive analytics data."""
        usage_percentage = 0
        if self.usage_limit and self.usage_limit > 0:
            usage_percentage = min(100, (self.usage_count / self.usage_limit) * 100)
        
        return {
            'total_uses': self.usage_count,
            'usage_limit': self.usage_limit,
            'usage_percentage': round(usage_percentage, 1),
            'remaining_uses': self.usage_limit - self.usage_count if self.usage_limit else None,
            'is_expired': not self.is_currently_valid,
            'days_until_expiry': self._days_until_expiry(),
            'discount_type': self.discount_type,
            'discount_value': float(self.discount_value)
        }
    
    def _days_until_expiry(self):
        """Helper to calculate days until expiry."""
        if not self.end_date:
            return None
        
        from django.utils import timezone
        now = timezone.now()
        if self.end_date <= now:
            return 0  # Already expired
        
        delta = self.end_date - now
        return delta.days
    
    def calculate_discount_amount(self, amount):
        """🚀 ENTERPRISE: Calculate discount amount for a given purchase amount."""
        if not self.is_currently_valid:
            return 0
        
        # Check minimum purchase requirement
        if self.min_purchase and amount < self.min_purchase:
            return 0
        
        if self.discount_type == 'percentage':
            discount = amount * (self.discount_value / 100)
        else:  # fixed
            discount = self.discount_value
        
        # Apply maximum discount limit
        if self.max_discount:
            discount = min(discount, self.max_discount)
        
        # Ensure discount doesn't exceed the purchase amount
        return min(discount, amount)
    
    def can_be_used_for_order(self, order_total, event_id):
        """
        🚀 ENTERPRISE: Comprehensive validation for coupon usage.
        
        Returns:
            tuple: (can_use: bool, message: str)
        """
        # 1. Basic validity check
        if not self.is_currently_valid:
            if self.status != 'active':
                return False, f"El cupón está {self.get_status_display().lower()}"
            if not self.is_active:
                return False, "El cupón está desactivado"
            if self.usage_limit and self.usage_count >= self.usage_limit:
                return False, "El cupón ha alcanzado su límite de uso"
            
            from django.utils import timezone
            now = timezone.now()
            if self.start_date and now < self.start_date:
                return False, f"El cupón será válido desde {self.start_date.strftime('%d/%m/%Y %H:%M')}"
            if self.end_date and now > self.end_date:
                return False, f"El cupón expiró el {self.end_date.strftime('%d/%m/%Y %H:%M')}"
        
        # 2. Minimum purchase validation
        if self.min_purchase and order_total < self.min_purchase:
            return False, f"Compra mínima requerida: ${self.min_purchase}"
        
        # 3. Event applicability validation
        if not self._is_applicable_to_event(event_id):
            if self.is_global:
                return False, "El cupón no aplica para este evento"
            else:
                return False, "El cupón es específico para otro evento"
        
        # 4. Usage limit validation (with tolerance for concurrent requests)
        if self.usage_limit:
            # Check with small buffer for race conditions
            remaining_uses = self.usage_limit - self.usage_count
            if remaining_uses <= 0:
                return False, "El cupón ha alcanzado su límite de uso"
        
        # 5. Calculate discount to ensure it's meaningful
        discount = self.calculate_discount_amount(order_total)
        if discount <= 0:
            return False, "El cupón no genera descuento para esta compra"
        
        return True, "Cupón válido"
    
    def _is_applicable_to_event(self, event_id):
        """🚀 ENTERPRISE: Check if coupon applies to specific event."""
        # Validate event_id is provided
        if not event_id:
            return False
        
        # Global coupons apply to all events of the organizer
        if self.is_global:
            # Verify event belongs to same organizer
            try:
                from apps.events.models import Event
                event = Event.objects.get(id=event_id)
                return event.organizer_id == self.organizer_id
            except Event.DoesNotExist:
                return False
        
        # Local coupons apply only to specific events
        applicable_events = self.get_applicable_events()
        if applicable_events is None:
            return True  # Shouldn't happen, but safe fallback
        
        return str(event_id) in [str(eid) for eid in applicable_events]
    
    def increment_usage(self):
        """🚀 ENTERPRISE: Atomic increment of usage count."""
        from django.db.models import F
        from django.db import transaction
        
        with transaction.atomic():
            # Use atomic F() expression to prevent race conditions
            updated_rows = Coupon.objects.filter(
                id=self.id,
                usage_count__lt=F('usage_limit') if self.usage_limit else True
            ).update(
                usage_count=F('usage_count') + 1
            )
            
            if updated_rows == 0:
                raise ValueError("No se pudo incrementar el uso del cupón (límite alcanzado o cupón no encontrado)")
            
            # Refresh instance to get updated values
            self.refresh_from_db()
    
    def reserve_usage_for_order(self, order):
        """🚀 ENTERPRISE: Reserve coupon usage during checkout."""
        from apps.events.models import CouponHold
        from django.utils import timezone
        from datetime import timedelta
        
        # Check if already reserved for this order
        existing_hold = CouponHold.objects.filter(
            coupon=self, 
            order=order, 
            released=False,
            expires_at__gt=timezone.now()
        ).first()
        
        if existing_hold:
            return existing_hold
        
        # Create new hold
        expires_at = timezone.now() + timedelta(minutes=15)  # 15 min expiry
        hold = CouponHold.objects.create(
            coupon=self,
            order=order,
            expires_at=expires_at
        )
        
        return hold
    
    def release_usage_for_order(self, order):
        """🚀 ENTERPRISE: Release coupon usage reservation."""
        from apps.events.models import CouponHold
        
        holds = CouponHold.objects.filter(
            coupon=self,
            order=order,
            released=False
        )
        
        for hold in holds:
            hold.release()
    
    def confirm_usage_for_order(self, order):
        """🚀 ENTERPRISE: Confirm coupon usage after successful payment."""
        from apps.events.models import CouponHold
        
        # Find active hold
        hold = CouponHold.objects.filter(
            coupon=self,
            order=order,
            released=False
        ).first()
        
        if not hold:
            raise ValueError("No hay reserva activa de cupón para esta orden")
        
        # Increment usage atomically
        self.increment_usage()
        
        # Mark hold as used
        hold.confirmed = True
        hold.save()
    
    def apply_to_multiple_events(self, event_ids):
        """Helper method to set multiple events for this coupon."""
        self.events_list = event_ids
        self.save()
    
    def get_applicable_events(self):
        """
        Get list of applicable event IDs.
        Returns None if applicable to all events (GLOBAL), otherwise returns list of IDs (LOCAL).
        
        🚀 ENTERPRISE: Simplified logic after migration 0019 removed legacy 'event' field
        """
        # 🚀 ENTERPRISE: Use events_list field for Global vs Local logic
        # events_list = None -> GLOBAL (applies to all organizer events)
        # events_list = [event_id] -> LOCAL (applies to specific event)
        return self.events_list


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


class EmailLog(BaseModel):
    """Audit log for all outgoing emails related to orders and tickets."""

    STATUS_CHOICES = (
        ('pending', _('Pending')),
        ('sent', _('Sent')),
        ('failed', _('Failed')),
        ('skipped', _('Skipped')),
    )

    order = models.ForeignKey(
        'Order',
        on_delete=models.CASCADE,
        related_name='email_logs',
        verbose_name=_('order'),
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(
        'Ticket',
        on_delete=models.SET_NULL,
        related_name='email_logs',
        verbose_name=_('ticket'),
        null=True,
        blank=True,
    )
    to_email = models.EmailField(_('to email'))
    subject = models.CharField(_('subject'), max_length=255)
    template = models.CharField(_('template'), max_length=100, blank=True)
    status = models.CharField(_('status'), max_length=20, choices=STATUS_CHOICES, default='pending')
    attempts = models.PositiveIntegerField(_('attempts'), default=0)
    error = models.TextField(_('error'), blank=True)
    provider_message_id = models.CharField(_('provider message id'), max_length=255, blank=True)
    sent_at = models.DateTimeField(_('sent at'), null=True, blank=True)
    metadata = models.JSONField(_('metadata'), default=dict, blank=True)

    class Meta:
        verbose_name = _('email log')
        verbose_name_plural = _('email logs')
        indexes = [
            models.Index(fields=['to_email', 'status']),
            models.Index(fields=['order']),
            models.Index(fields=['ticket']),
        ]

    def __str__(self):
        ref = self.ticket.ticket_number if self.ticket_id else (self.order.order_number if self.order_id else '-')
        return f"Email to {self.to_email} [{self.status}] ({ref})"


class SimpleBooking(BaseModel):
    """Simple booking model for free/simple events without complex ticketing."""
    
    STATUS_CHOICES = (
        ('pending', _('Pending Approval')),
        ('confirmed', _('Confirmed')),
        ('cancelled', _('Cancelled')),
        ('attended', _('Attended')),
    )
    
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='simple_bookings',
        verbose_name=_("event")
    )
    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email"))
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    notes = models.TextField(_("notes"), blank=True)
    
    # Approval workflow
    approved_by = models.ForeignKey(
        'organizers.OrganizerUser',
        on_delete=models.SET_NULL,
        related_name='approved_bookings',
        verbose_name=_("approved by"),
        null=True,
        blank=True
    )
    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    
    # Check-in
    checked_in = models.BooleanField(_("checked in"), default=False)
    check_in_time = models.DateTimeField(_("check in time"), null=True, blank=True)
    
    class Meta:
        verbose_name = _("simple booking")
        verbose_name_plural = _("simple bookings")
        unique_together = ['event', 'email']  # One booking per email per event
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.event.title}"
    
    @property
    def attendee_name(self):
        """Return the attendee's full name."""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_pending(self):
        """Return True if booking is pending approval."""
        return self.status == 'pending'
    
    @property
    def is_confirmed(self):
        """Return True if booking is confirmed."""
        return self.status == 'confirmed'


class TicketRequest(BaseModel):
    """Model for ticket requests that require approval before purchase/access."""
    
    STATUS_CHOICES = (
        ('pending', _('Pending Approval')),
        ('approved', _('Approved - Can Purchase')),
        ('rejected', _('Rejected')),
        ('purchased', _('Purchased')),
        ('cancelled', _('Cancelled')),
    )
    
    # What they're requesting
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='ticket_requests',
        verbose_name=_("event")
    )
    ticket_tier = models.ForeignKey(
        TicketTier,
        on_delete=models.CASCADE,
        related_name='ticket_requests',
        verbose_name=_("ticket tier"),
        null=True,
        blank=True
    )
    ticket_category = models.ForeignKey(
        TicketCategory,
        on_delete=models.CASCADE,
        related_name='ticket_requests',
        verbose_name=_("ticket category"),
        null=True,
        blank=True
    )
    quantity = models.PositiveIntegerField(_("quantity"), default=1)
    
    # Requester information
    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email"))
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    message = models.TextField(_("message"), blank=True, help_text=_("Optional message from requester"))
    
    # Status and workflow
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Approval workflow
    reviewed_by = models.ForeignKey(
        'organizers.OrganizerUser',
        on_delete=models.SET_NULL,
        related_name='reviewed_ticket_requests',
        verbose_name=_("reviewed by"),
        null=True,
        blank=True
    )
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True)
    review_notes = models.TextField(_("review notes"), blank=True)
    
    # Purchase tracking (for approved paid tickets)
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        related_name='ticket_requests',
        verbose_name=_("order"),
        null=True,
        blank=True
    )
    simple_booking = models.ForeignKey(
        SimpleBooking,
        on_delete=models.SET_NULL,
        related_name='ticket_requests',
        verbose_name=_("simple booking"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("ticket request")
        verbose_name_plural = _("ticket requests")
        unique_together = ['event', 'email', 'ticket_tier']  # One request per email per ticket type
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.event.title} ({self.get_status_display()})"
    
    @property
    def requester_name(self):
        """Return the requester's full name."""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_pending(self):
        """Return True if request is pending approval."""
        return self.status == 'pending'
    
    @property
    def is_approved(self):
        """Return True if request is approved."""
        return self.status == 'approved'
    
    @property
    def is_rejected(self):
        """Return True if request is rejected."""
        return self.status == 'rejected'
    
    @property
    def target_name(self):
        """Return the name of what's being requested."""
        if self.ticket_tier:
            return self.ticket_tier.name
        elif self.ticket_category:
            return self.ticket_category.name
        return "Entrada al evento" 