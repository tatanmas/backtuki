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
    
    # Pricing (enterprise multi-tier)
    PRICING_MODE_CHOICES = (
        ('per_person', _('Per Person')),
        ('per_booking', _('Per Booking')),
    )
    
    pricing_mode = models.CharField(
        _("pricing mode"),
        max_length=20,
        choices=PRICING_MODE_CHOICES,
        default='per_person',
        help_text=_("Whether pricing is per person or per booking/group")
    )
    
    # Base pricing (global defaults)
    price = models.DecimalField(
        _("base price (adult)"),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Base price for adults (or per booking if pricing_mode=per_booking)")
    )
    
    child_price = models.DecimalField(
        _("child price"),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Base price for children (only if is_child_priced=True)")
    )
    
    is_child_priced = models.BooleanField(
        _("charge for children"),
        default=False,
        help_text=_("Whether children are charged (if False, child_price is ignored)")
    )
    
    infant_price = models.DecimalField(
        _("infant price"),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Base price for infants (only if is_infant_priced=True)")
    )
    
    is_infant_priced = models.BooleanField(
        _("charge for infants"),
        default=False,
        help_text=_("Whether infants are charged (if False, infant_price is ignored)")
    )
    
    currency = models.CharField(
        _("currency"),
        max_length=3,
        default='CLP',
        help_text=_("Currency code (ISO 4217)")
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
    
    # Capacity counting rules
    CAPACITY_COUNT_CHOICES = (
        ('all', _('All (adults + children + infants)')),
        ('exclude_infants', _('Adults + children only')),
        ('adults_only', _('Adults only')),
    )
    
    capacity_count_rule = models.CharField(
        _("capacity count rule"),
        max_length=20,
        choices=CAPACITY_COUNT_CHOICES,
        default='all',
        help_text=_("Which participant types count toward capacity limits")
    )
    
    # Booking horizon
    booking_horizon_days = models.PositiveIntegerField(
        _("booking horizon (days)"),
        default=90,
        validators=[MinValueValidator(1)],
        help_text=_("How many days into the future customers can book (instances are materialized within this window)")
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
    
    # 🚀 ENTERPRISE: Soft delete and activation control
    is_active = models.BooleanField(
        _("is active"),
        default=True,
        help_text=_("Whether this experience is active (visible publicly)")
    )
    deleted_at = models.DateTimeField(
        _("deleted at"),
        null=True,
        blank=True,
        help_text=_("When this experience was soft-deleted (null if not deleted)")
    )
    
    class Meta:
        verbose_name = _("experience")
        verbose_name_plural = _("experiences")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organizer', 'status']),
            models.Index(fields=['is_free_tour', 'status']),
            models.Index(fields=['slug']),
            models.Index(fields=['is_active', 'deleted_at']),
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
    
    # Pricing overrides (null = use experience base pricing)
    override_adult_price = models.DecimalField(
        _("override adult price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=_("Override adult price for this instance (null = use experience base)")
    )
    
    override_child_price = models.DecimalField(
        _("override child price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=_("Override child price for this instance")
    )
    
    override_infant_price = models.DecimalField(
        _("override infant price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=_("Override infant price for this instance")
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


class ExperienceResource(BaseModel):
    """Resources/equipment that can be added to an experience (e.g., kayaks, bikes)."""
    
    RESOURCE_TYPE_CHOICES = (
        ('base', _('Base (always included)')),
        ('required_exclusive', _('Required (choose one)')),
        ('required_multiple', _('Required (choose quantity)')),
        ('optional', _('Optional add-on')),
    )
    
    experience = models.ForeignKey(
        Experience,
        on_delete=models.CASCADE,
        related_name='resources',
        verbose_name=_("experience")
    )
    
    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    
    resource_type = models.CharField(
        _("resource type"),
        max_length=20,
        choices=RESOURCE_TYPE_CHOICES,
        default='optional'
    )
    
    # Grouping (for exclusive choices: "Kayak Type" group with "Single"/"Double" options)
    group_id = models.CharField(
        _("group ID"),
        max_length=100,
        blank=True,
        help_text=_("Group identifier for related resources (e.g., 'kayak_type')")
    )
    
    # Pricing
    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Additional price for this resource")
    )
    
    is_per_person = models.BooleanField(
        _("is per person"),
        default=False,
        help_text=_("Whether price is multiplied by number of people using it")
    )
    
    # Capacity/inventory
    people_per_unit = models.PositiveIntegerField(
        _("people per unit"),
        default=1,
        help_text=_("How many people can use one unit (e.g., 2 for tandem kayak)")
    )
    
    available_quantity = models.PositiveIntegerField(
        _("available quantity"),
        null=True,
        blank=True,
        help_text=_("Total units available (null = unlimited)")
    )
    
    # Display
    image_url = models.URLField(_("image URL"), blank=True)
    display_order = models.PositiveIntegerField(_("display order"), default=0)
    
    is_active = models.BooleanField(_("is active"), default=True)
    
    class Meta:
        verbose_name = _("experience resource")
        verbose_name_plural = _("experience resources")
        ordering = ['experience', 'display_order', 'name']
        indexes = [
            models.Index(fields=['experience', 'is_active']),
            models.Index(fields=['group_id']),
        ]
    
    def __str__(self):
        return f"{self.experience.title} - {self.name}"


class ExperienceDatePriceOverride(BaseModel):
    """Price overrides for specific dates (highest precedence)."""
    
    experience = models.ForeignKey(
        Experience,
        on_delete=models.CASCADE,
        related_name='date_price_overrides',
        verbose_name=_("experience")
    )
    
    date = models.DateField(_("date"))
    
    # Time range (optional: applies only to instances within this time range on that date)
    start_time = models.TimeField(_("start time"), null=True, blank=True)
    end_time = models.TimeField(_("end time"), null=True, blank=True)
    
    # Pricing overrides
    override_adult_price = models.DecimalField(
        _("override adult price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    override_child_price = models.DecimalField(
        _("override child price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    override_infant_price = models.DecimalField(
        _("override infant price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # Capacity override
    override_capacity = models.PositiveIntegerField(
        _("override capacity"),
        null=True,
        blank=True
    )
    
    notes = models.TextField(_("notes"), blank=True)
    
    class Meta:
        verbose_name = _("experience date price override")
        verbose_name_plural = _("experience date price overrides")
        ordering = ['experience', 'date', 'start_time']
        indexes = [
            models.Index(fields=['experience', 'date']),
        ]
    
    def __str__(self):
        return f"{self.experience.title} - {self.date}"


class ExperienceReservation(BaseModel):
    """
    Transactional reservation entity (checkout session + confirmed booking).
    Similar to Order but specific to experiences with holds.
    """
    
    STATUS_CHOICES = (
        ('pending', _('Pending')),
        ('paid', _('Paid')),
        ('cancelled', _('Cancelled')),
        ('expired', _('Expired')),
        ('refunded', _('Refunded')),
    )
    
    # Unique reservation ID (for frontend tracking)
    reservation_id = models.CharField(
        _("reservation ID"),
        max_length=100,
        unique=True,
        db_index=True
    )
    
    experience = models.ForeignKey(
        Experience,
        on_delete=models.CASCADE,
        related_name='reservations',
        verbose_name=_("experience")
    )
    
    instance = models.ForeignKey(
        TourInstance,
        on_delete=models.CASCADE,
        related_name='reservations',
        verbose_name=_("tour instance")
    )
    
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Participants
    adult_count = models.PositiveIntegerField(_("adult count"), default=1)
    child_count = models.PositiveIntegerField(_("child count"), default=0)
    infant_count = models.PositiveIntegerField(_("infant count"), default=0)
    
    # Contact info (snapshot)
    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email"))
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    
    # User account (optional)
    user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='experience_reservations',
        verbose_name=_("user"),
        null=True,
        blank=True
    )
    
    # 🚀 ENTERPRISE: Platform flow tracking (analogous to Order.flow)
    flow = models.ForeignKey(
        'core.PlatformFlow',
        on_delete=models.SET_NULL,
        related_name='experience_reservations',
        verbose_name=_("platform flow"),
        null=True,
        blank=True,
        help_text=_("Platform flow tracking this reservation (for traceability)")
    )
    
    # Pricing snapshot (at time of reservation)
    subtotal = models.DecimalField(
        _("subtotal"),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    service_fee = models.DecimalField(
        _("service fee"),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    discount = models.DecimalField(
        _("discount"),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    total = models.DecimalField(
        _("total"),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    
    # Pricing breakdown (JSON snapshot)
    pricing_details = models.JSONField(
        _("pricing details"),
        default=dict,
        blank=True,
        help_text=_("Snapshot of pricing calculation (adult_price, child_price, resources, etc.)")
    )
    
    # Resources selected (JSON snapshot)
    selected_resources = models.JSONField(
        _("selected resources"),
        default=list,
        blank=True,
        help_text=_("List of {resource_id, resource_name, quantity, price}")
    )
    
    # Capacity rule snapshot
    capacity_count_rule = models.CharField(
        _("capacity count rule"),
        max_length=20,
        default='all'
    )
    
    # Expiration (for pending reservations)
    expires_at = models.DateTimeField(
        _("expires at"),
        null=True,
        blank=True,
        help_text=_("When this reservation expires if not paid (null = no expiry)")
    )
    
    # Payment tracking
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    
    # Notes
    notes = models.TextField(_("notes"), blank=True)
    
    class Meta:
        verbose_name = _("experience reservation")
        verbose_name_plural = _("experience reservations")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reservation_id']),
            models.Index(fields=['experience', 'status']),
            models.Index(fields=['instance', 'status']),
            models.Index(fields=['email']),
            models.Index(fields=['user']),
            models.Index(fields=['status', 'expires_at']),
        ]
    
    def __str__(self):
        return f"{self.reservation_id} - {self.experience.title} ({self.status})"
    
    def get_capacity_units(self):
        """Calculate how many capacity units this reservation consumes."""
        rule = self.capacity_count_rule
        if rule == 'all':
            return self.adult_count + self.child_count + self.infant_count
        elif rule == 'exclude_infants':
            return self.adult_count + self.child_count
        elif rule == 'adults_only':
            return self.adult_count
        return self.adult_count + self.child_count + self.infant_count  # default


class ExperienceCapacityHold(BaseModel):
    """
    Hold on capacity for a tour instance (prevents overbooking).
    Similar to TicketHold but for experience capacity.
    """
    
    instance = models.ForeignKey(
        TourInstance,
        on_delete=models.CASCADE,
        related_name='capacity_holds',
        verbose_name=_("tour instance")
    )
    
    reservation = models.ForeignKey(
        ExperienceReservation,
        on_delete=models.CASCADE,
        related_name='capacity_holds',
        verbose_name=_("reservation")
    )
    
    capacity_units = models.PositiveIntegerField(
        _("capacity units"),
        help_text=_("Number of capacity units held (calculated from participants + rule)")
    )
    
    expires_at = models.DateTimeField(_("expires at"))
    
    released = models.BooleanField(
        _("released"),
        default=False,
        help_text=_("Whether this hold has been released (expired or cancelled)")
    )
    
    released_at = models.DateTimeField(_("released at"), null=True, blank=True)
    
    class Meta:
        verbose_name = _("experience capacity hold")
        verbose_name_plural = _("experience capacity holds")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['instance', 'released', 'expires_at']),
            models.Index(fields=['reservation']),
        ]
    
    def __str__(self):
        return f"Hold {self.capacity_units} units for {self.instance} (expires {self.expires_at})"


class ExperienceResourceHold(BaseModel):
    """
    Hold on resource inventory (prevents double-booking of limited resources).
    """
    
    resource = models.ForeignKey(
        ExperienceResource,
        on_delete=models.CASCADE,
        related_name='holds',
        verbose_name=_("resource")
    )
    
    reservation = models.ForeignKey(
        ExperienceReservation,
        on_delete=models.CASCADE,
        related_name='resource_holds',
        verbose_name=_("reservation")
    )
    
    instance = models.ForeignKey(
        TourInstance,
        on_delete=models.CASCADE,
        related_name='resource_holds',
        verbose_name=_("tour instance")
    )
    
    quantity = models.PositiveIntegerField(
        _("quantity"),
        help_text=_("Number of units held")
    )
    
    expires_at = models.DateTimeField(_("expires at"))
    
    released = models.BooleanField(
        _("released"),
        default=False
    )
    
    released_at = models.DateTimeField(_("released at"), null=True, blank=True)
    
    class Meta:
        verbose_name = _("experience resource hold")
        verbose_name_plural = _("experience resource holds")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['resource', 'instance', 'released', 'expires_at']),
            models.Index(fields=['reservation']),
        ]
    
    def __str__(self):
        return f"Hold {self.quantity}x {self.resource.name} for {self.instance}"

