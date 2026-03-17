"""Models for accommodations (alojamientos)."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator

from core.models import BaseModel
from apps.organizers.models import Organizer


class RentalHub(BaseModel):
    """
    Central de arrendamiento: landing de un complejo (ej. Arenas de Playa Blanca).
    Agrupa accommodations por slug para la página pública.
    """
    slug = models.SlugField(_("slug"), max_length=255, unique=True, db_index=True)
    name = models.CharField(_("name"), max_length=255)
    short_description = models.CharField(_("short description"), max_length=500, blank=True)
    description = models.TextField(_("description"), blank=True)
    hero_image = models.URLField(_("hero image URL"), max_length=500, blank=True)
    hero_media_id = models.UUIDField(
        _("hero image from media library"),
        null=True,
        blank=True,
        help_text=_("MediaAsset UUID for hero image (superadmin library)"),
    )
    gallery = models.JSONField(
        _("gallery image URLs"),
        default=list,
        help_text=_("List of image URLs for the hub gallery"),
    )
    gallery_media_ids = models.JSONField(
        _("gallery media asset IDs"),
        default=list,
        blank=True,
        help_text=_("List of MediaAsset UUIDs for the hub gallery (superadmin library)"),
    )
    meta_title = models.CharField(_("meta title (SEO)"), max_length=255, blank=True)
    meta_description = models.CharField(_("meta description (SEO)"), max_length=500, blank=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    min_nights = models.PositiveIntegerField(
        _("minimum nights"),
        null=True,
        blank=True,
        help_text=_("Minimum number of nights for a booking at this hub. Units inherit if they have no own rule."),
    )
    units_section_title = models.CharField(
        _("units section title"),
        max_length=255,
        default="Nuestros Departamentos",
        blank=True,
        help_text=_("Title of the units list section on the hub landing (e.g. 'Nuestros Departamentos', 'Nuestras Casas')."),
    )
    units_section_subtitle = models.CharField(
        _("units section subtitle"),
        max_length=500,
        default="Selecciona la unidad perfecta para tu estadía",
        blank=True,
        help_text=_("Subtitle below the units section title on the hub landing."),
    )
    whatsapp_message_templates = models.JSONField(
        _("WhatsApp reservation message templates"),
        default=dict,
        blank=True,
        help_text=_(
            "Optional overrides for reservation flow messages (central level). "
            "Keys: reservation_request, customer_waiting, etc. Empty = use platform default."
        ),
    )
    default_whatsapp_group = models.ForeignKey(
        "whatsapp.WhatsAppChat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rental_hub_default_for",
        verbose_name=_("Default WhatsApp group"),
        limit_choices_to={"type": "group"},
        help_text=_("WhatsApp group for reservation coordination. Units without their own group use this."),
    )

    class Meta:
        verbose_name = _("Rental hub")
        verbose_name_plural = _("Rental hubs")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Hotel(BaseModel):
    """
    Hotel: landing con hero y galería; agrupa habitaciones (Accommodations).
    Ubicación y amenidades a nivel hotel para herencia por habitación.
    """
    slug = models.SlugField(_("slug"), max_length=255, unique=True, db_index=True)
    name = models.CharField(_("name"), max_length=255)
    short_description = models.CharField(_("short description"), max_length=500, blank=True)
    description = models.TextField(_("description"), blank=True)
    hero_media_id = models.UUIDField(
        _("hero image from media library"),
        null=True,
        blank=True,
        help_text=_("MediaAsset UUID for hero image (superadmin library)"),
    )
    gallery_media_ids = models.JSONField(
        _("gallery media asset IDs"),
        default=list,
        blank=True,
        help_text=_("List of MediaAsset UUIDs for the hotel gallery (superadmin library)"),
    )
    meta_title = models.CharField(_("meta title (SEO)"), max_length=255, blank=True)
    meta_description = models.CharField(_("meta description (SEO)"), max_length=500, blank=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    # Location and amenities for inheritance by rooms
    location_name = models.CharField(_("location name"), max_length=255, blank=True)
    location_address = models.TextField(_("address"), blank=True)
    city = models.CharField(_("city / region"), max_length=255, blank=True)
    country = models.CharField(_("country"), max_length=255, default="Chile")
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    amenities = models.JSONField(
        _("amenities"),
        default=list,
        blank=True,
        help_text=_("List of amenity strings; rooms can inherit these."),
    )
    external_id = models.CharField(
        _("external ID for channel manager"),
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_("Optional mapping for channel manager integration."),
    )
    min_nights = models.PositiveIntegerField(
        _("minimum nights"),
        null=True,
        blank=True,
        help_text=_("Minimum number of nights for a booking. Rooms inherit if they have no own rule."),
    )

    # Comisión / forma de cobro (las habitaciones heredan si no definen el suyo)
    PAYMENT_MODEL_CHOICES = [
        ("full_platform", _("Full platform (guest pays total online; Tuki retains commission)")),
        ("commission_only", _("Commission only (guest pays Tuki commission online; rest at hotel)")),
    ]
    payment_model = models.CharField(
        _("payment model"),
        max_length=20,
        choices=PAYMENT_MODEL_CHOICES,
        default="full_platform",
        blank=True,
        help_text=_("full_platform: guest pays total online. commission_only: guest pays commission online, rest at hotel."),
    )
    tuki_commission_rate = models.DecimalField(
        _("Tuki commission rate"),
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text=_("Platform commission rate e.g. 0.20 = 20%%. Null = use platform default."),
    )
    whatsapp_message_templates = models.JSONField(
        _("WhatsApp reservation message templates"),
        default=dict,
        blank=True,
        help_text=_(
            "Optional overrides for reservation flow messages (hotel level). "
            "Rooms inherit; room override wins. Keys: reservation_request, customer_waiting, etc."
        ),
    )
    default_whatsapp_group = models.ForeignKey(
        "whatsapp.WhatsAppChat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hotel_default_for",
        verbose_name=_("Default WhatsApp group"),
        limit_choices_to={"type": "group"},
        help_text=_("WhatsApp group for reservation coordination. Rooms without their own group use this."),
    )

    class Meta:
        verbose_name = _("Hotel")
        verbose_name_plural = _("Hotels")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Accommodation(BaseModel):
    """Alojamiento: cabaña, casa, departamento, etc. Con reseñas y amenities."""

    STATUS_CHOICES = [
        ("draft", _("Draft")),
        ("published", _("Published")),
        ("cancelled", _("Cancelled")),
    ]
    PROPERTY_TYPE_CHOICES = [
        ("cabin", _("Cabin")),
        ("house", _("House")),
        ("apartment", _("Apartment")),
        ("hotel", _("Hotel")),
        ("hostel", _("Hostel")),
        ("villa", _("Villa")),
        ("other", _("Other")),
    ]

    title = models.CharField(_("title"), max_length=255)
    slug = models.SlugField(_("slug"), max_length=255, unique=True, db_index=True)
    description = models.TextField(_("description"), blank=True)
    short_description = models.CharField(_("short description"), max_length=500, blank=True)

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        db_index=True,
    )
    # Código público (tuqui1-a1b2c3): generado al publicar; no obligatorio en JSON
    public_code = models.CharField(
        _("public code"),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Unique code generated when published (e.g. tuqui1-a1b2c3). Not required for JSON/create."),
    )
    # Número de orden (1-based) para listados; se asigna al publicar si no está definido
    display_order = models.PositiveIntegerField(
        _("display order"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Order number starting from 1. Assigned automatically when published if not set."),
    )
    # Prefijo opcional del código público (ej. Tuki-PV para Pedra Verde → Tuki-PV-001)
    public_code_prefix = models.CharField(
        _("public code prefix"),
        max_length=30,
        blank=True,
        db_index=True,
        help_text=_("Optional prefix for public code (e.g. Tuki-PV → Tuki-PV-001). If blank, uses default tuqui{N}-{random}."),
    )
    property_type = models.CharField(
        _("property type"),
        max_length=20,
        choices=PROPERTY_TYPE_CHOICES,
        default="cabin",
    )

    organizer = models.ForeignKey(
        Organizer,
        on_delete=models.CASCADE,
        related_name="accommodations",
        verbose_name=_("organizer"),
        null=True,
        blank=True,
    )

    # Location
    location_name = models.CharField(_("location name"), max_length=255, blank=True)
    location_address = models.TextField(_("address"), blank=True)
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    country = models.CharField(_("country"), max_length=255, default="Chile")
    city = models.CharField(_("city / region"), max_length=255, blank=True)

    # Capacity
    guests = models.PositiveIntegerField(_("max guests"), default=2, validators=[MinValueValidator(1)])
    bedrooms = models.PositiveIntegerField(_("bedrooms"), default=1, validators=[MinValueValidator(0)])
    # Bathrooms: industry-standard full (toilet + sink + shower/bath) vs half (toilet + sink only; powder room)
    full_bathrooms = models.PositiveIntegerField(
        _("full bathrooms"),
        default=1,
        validators=[MinValueValidator(0)],
        help_text=_("Full bathrooms: toilet, sink, and shower or bathtub."),
    )
    half_bathrooms = models.PositiveIntegerField(
        _("half bathrooms"),
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Half bathrooms (powder rooms): toilet and sink only, no shower."),
    )
    beds = models.PositiveIntegerField(_("beds"), default=1, validators=[MinValueValidator(0)], blank=True, null=True)

    # Pricing (per night). Precio mostrado al huésped; la plataforma retiene 20%, neto anfitrión = 80%.
    price = models.DecimalField(
        _("price per night (guest-facing)"),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Precio por noche mostrado al huésped. Plataforma retiene 20%; anfitrión recibe 80%."),
    )
    currency = models.CharField(_("currency"), max_length=3, default="CLP")

    # Amenities
    amenities = models.JSONField(
        _("amenities"),
        default=list,
        help_text=_("List of amenity strings, e.g. ['WiFi', 'Cocina', 'Parrilla']"),
    )
    not_amenities = models.JSONField(
        _("not available"),
        default=list,
        help_text=_("List of things not available, e.g. ['TV', 'Lavadora']"),
    )

    # Media: list of image URLs (from MediaAsset or external)
    images = models.JSONField(_("image URLs"), default=list)
    gallery_media_ids = models.JSONField(
        _("gallery media asset IDs"),
        default=list,
        help_text=_("UUIDs of MediaAsset for gallery (optional)"),
    )
    gallery_items = models.JSONField(
        _("gallery items with order and room category"),
        default=list,
        blank=True,
        help_text=_(
            "List of {media_id, room_category, sort_order, is_principal}. "
            "sort_order = global order in gallery; is_principal = image for cards/listings. "
            "room_category from ROOM_CATEGORIES or null. gallery_media_ids synced on save."
        ),
    )

    # Rating (computed or manual)
    rating_avg = models.DecimalField(
        _("average rating"),
        max_digits=2,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    review_count = models.PositiveIntegerField(_("review count"), default=0)

    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True, db_index=True)

    # Rental hub / central de arrendamiento (ej. Playa Blanca)
    rental_hub = models.ForeignKey(
        RentalHub,
        on_delete=models.SET_NULL,
        related_name="accommodations",
        verbose_name=_("rental hub"),
        null=True,
        blank=True,
        db_index=True,
    )
    # Por central: Playa Blanca usa A1, A2, B, C; otras centrales pueden usar otros códigos (Estudio, 1D, etc.)
    unit_type = models.CharField(
        _("unit type"),
        max_length=30,
        blank=True,
        db_index=True,
        help_text=_("Código de tipo de unidad según la central (ej. A1, A2, B, C en Playa Blanca; Estudio, 1D en otra)."),
    )
    tower = models.CharField(
        _("tower"),
        max_length=30,
        blank=True,
        db_index=True,
        help_text=_("Torre o bloque (ej. A, B). Depende de la central."),
    )
    floor = models.PositiveIntegerField(
        _("floor"),
        null=True,
        blank=True,
        help_text=_("Piso"),
    )
    unit_number = models.CharField(
        _("unit number"),
        max_length=20,
        blank=True,
        db_index=True,
        help_text=_("Número de departamento (ej. 101, 803)"),
    )
    square_meters = models.DecimalField(
        _("square meters"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=_("Metraje total en m²"),
    )

    # Hotel / habitación
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.SET_NULL,
        related_name="rooms",
        verbose_name=_("hotel"),
        null=True,
        blank=True,
        db_index=True,
    )
    inherit_location_from_hotel = models.BooleanField(
        _("inherit location from hotel"),
        default=True,
        help_text=_("When True, public API uses hotel location when room has no own location."),
    )
    inherit_amenities_from_hotel = models.BooleanField(
        _("inherit amenities from hotel"),
        default=True,
        help_text=_("When True, public API merges hotel amenities with room amenities."),
    )
    room_type_code = models.CharField(
        _("room type code for channel manager"),
        max_length=30,
        blank=True,
        db_index=True,
        help_text=_("e.g. STD, DBL, SUITE for future channel manager integration."),
    )
    external_id = models.CharField(
        _("external ID for channel manager"),
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_("Optional mapping for channel manager / PMS room or rate ID."),
    )
    min_nights = models.PositiveIntegerField(
        _("minimum nights"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=_("Minimum number of nights for a booking. Overrides hub/hotel rule when set."),
    )

    # Comisión / forma de cobro (habitación prima sobre hotel; si no tiene, hereda del hotel)
    PAYMENT_MODEL_CHOICES = [
        ("full_platform", _("Full platform (guest pays total online)")),
        ("commission_only", _("Commission only (guest pays commission online, rest at property)")),
    ]
    payment_model = models.CharField(
        _("payment model"),
        max_length=20,
        choices=PAYMENT_MODEL_CHOICES,
        default="",
        blank=True,
        help_text=_("If blank and hotel_id set, inherits from hotel. Otherwise platform default."),
    )
    tuki_commission_rate = models.DecimalField(
        _("Tuki commission rate"),
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text=_("Platform commission e.g. 0.20 = 20%%. Room overrides hotel; null = inherit or default."),
    )
    whatsapp_message_templates = models.JSONField(
        _("WhatsApp reservation message templates"),
        default=dict,
        blank=True,
        help_text=_(
            "Optional overrides for reservation flow messages (room/unit level). "
            "Wins over hotel/central and platform. Keys: reservation_request, customer_waiting, etc."
        ),
    )

    class Meta:
        verbose_name = _("Accommodation")
        verbose_name_plural = _("Accommodations")
        ordering = ["-created_at"]

    def get_effective_min_nights(self):
        """
        Resolved minimum nights: accommodation-specific rule wins, then rental_hub, then hotel.
        Returns None if no rule is set at any level.
        """
        if self.min_nights is not None and self.min_nights >= 1:
            return self.min_nights
        if self.rental_hub_id and getattr(self.rental_hub, "min_nights", None) is not None:
            return self.rental_hub.min_nights
        if self.hotel_id and getattr(self.hotel, "min_nights", None) is not None:
            return self.hotel.min_nights
        return None

    def __str__(self):
        return self.title


class AccommodationExtraCharge(BaseModel):
    """
    Extra charge for an accommodation (e.g. linens, cleaning).
    code is unique per accommodation and immutable once created.
    """

    CHARGE_TYPE_CHOICES = [
        ("per_stay", _("Per stay")),
        ("per_night", _("Per night")),
    ]

    accommodation = models.ForeignKey(
        Accommodation,
        on_delete=models.CASCADE,
        related_name="extra_charges",
        verbose_name=_("accommodation"),
    )
    code = models.CharField(
        _("code"),
        max_length=64,
        help_text=_("Unique per accommodation; used in selected_options. Immutable once created."),
    )
    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    charge_type = models.CharField(
        _("charge type"),
        max_length=20,
        choices=CHARGE_TYPE_CHOICES,
        default="per_stay",
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(
        _("currency"),
        max_length=3,
        null=True,
        blank=True,
        help_text=_("Null = accommodation currency. If different from accommodation, rejected in v1."),
    )
    is_optional = models.BooleanField(
        _("optional"),
        default=True,
        help_text=_("True = guest chooses; False = always applied (mandatory)."),
    )
    default_quantity = models.PositiveIntegerField(
        _("default quantity"),
        default=1,
        help_text=_("For optional extras: default quantity in selector. Not used for mandatory."),
    )
    max_quantity = models.PositiveIntegerField(
        _("max quantity"),
        null=True,
        blank=True,
        help_text=_("Null = no cap. Only applies to optional extras."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    display_order = models.PositiveIntegerField(_("display order"), default=0)

    class Meta:
        verbose_name = _("Accommodation extra charge")
        verbose_name_plural = _("Accommodation extra charges")
        ordering = ["display_order", "name"]
        unique_together = [("accommodation", "code")]

    def __str__(self):
        return f"{self.accommodation.title} – {self.name} ({self.code})"


class AccommodationReview(models.Model):
    """Reseña de un alojamiento (autor, puntuación, texto, respuesta del anfitrión)."""

    id = models.BigAutoField(primary_key=True)
    accommodation = models.ForeignKey(
        Accommodation,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("accommodation"),
    )
    author_name = models.CharField(_("author name"), max_length=255)
    author_location = models.CharField(_("author location"), max_length=255, blank=True)
    rating = models.PositiveSmallIntegerField(
        _("rating"),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    text = models.TextField(_("review text"), blank=True)
    review_date = models.DateField(_("review date"), null=True, blank=True)
    stay_type = models.CharField(_("stay type"), max_length=100, blank=True)  # e.g. "Estadía de varias noches"
    host_reply = models.TextField(_("host reply"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Accommodation review")
        verbose_name_plural = _("Accommodation reviews")
        ordering = ["-review_date", "-created_at"]

    def __str__(self):
        return f"{self.author_name} – {self.accommodation.title} ({self.rating}★)"


class AccommodationReservation(BaseModel):
    """
    Reservation for an accommodation (WhatsApp flow: operator confirms then payment).
    Reuses Order/payment_processor; linked from WhatsAppReservationRequest.
    """

    STATUS_CHOICES = [
        ("pending", _("Pending")),
        ("paid", _("Paid")),
        ("cancelled", _("Cancelled")),
        ("expired", _("Expired")),
        ("refunded", _("Refunded")),
    ]

    reservation_id = models.CharField(
        _("reservation ID"),
        max_length=100,
        unique=True,
        db_index=True,
    )
    accommodation = models.ForeignKey(
        Accommodation,
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name=_("accommodation"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    check_in = models.DateField(_("check-in"))
    check_out = models.DateField(_("check-out"))
    guests = models.PositiveIntegerField(_("guests"), default=1, validators=[MinValueValidator(1)])

    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email"))
    phone = models.CharField(_("phone"), max_length=20, blank=True)

    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="accommodation_reservations",
        verbose_name=_("user"),
        null=True,
        blank=True,
    )

    total = models.DecimalField(
        _("total"),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(_("currency"), max_length=3, default="CLP")

    pricing_snapshot = models.JSONField(
        _("pricing snapshot"),
        null=True,
        blank=True,
        help_text=_("Immutable snapshot at reservation creation: base, extras, total. Legacy reservations have null."),
    )

    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)

    # 🚀 ENTERPRISE: Platform flow for audit trail (WhatsApp reservation → order → payment)
    flow = models.ForeignKey(
        "core.PlatformFlow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accommodation_reservations",
        verbose_name=_("platform flow"),
        help_text=_("Platform flow tracking this reservation (for traceability)"),
    )

    class Meta:
        verbose_name = _("Accommodation reservation")
        verbose_name_plural = _("Accommodation reservations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["reservation_id"]),
            models.Index(fields=["accommodation", "status"]),
            models.Index(fields=["check_in", "check_out"]),
        ]

    def __str__(self):
        return f"{self.reservation_id} - {self.accommodation.title} ({self.status})"


class AccommodationBlockedDate(models.Model):
    """
    Fecha bloqueada para un alojamiento (no disponible para reserva).
    Usado por centrales de arrendamiento para marcar fechas manualmente.
    """
    accommodation = models.ForeignKey(
        Accommodation,
        on_delete=models.CASCADE,
        related_name="blocked_dates",
        verbose_name=_("accommodation"),
    )
    date = models.DateField(_("date"), db_index=True)

    class Meta:
        verbose_name = _("Accommodation blocked date")
        verbose_name_plural = _("Accommodation blocked dates")
        unique_together = [("accommodation", "date")]
        ordering = ["accommodation", "date"]
        indexes = [
            models.Index(fields=["accommodation", "date"]),
        ]

    def __str__(self):
        return f"{self.accommodation.title} - {self.date}"
