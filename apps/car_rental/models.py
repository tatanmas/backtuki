"""Models for car rental (rent-a-car): companies, cars, blocked dates, reservations."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator

from core.models import BaseModel
from apps.organizers.models import Organizer


class CarRentalCompany(BaseModel):
    """
    Central de arrendamiento de autos (empresa rent-a-car).
    Agrupa autos; condiciones comunes (garantía, seguro, daños) heredables por auto.
    """
    name = models.CharField(_("name"), max_length=255)
    slug = models.SlugField(_("slug"), max_length=255, unique=True, db_index=True)
    short_description = models.CharField(_("short description"), max_length=500, blank=True)
    description = models.TextField(_("description"), blank=True)
    hero_media_id = models.UUIDField(
        _("hero image from media library"),
        null=True,
        blank=True,
        help_text=_("MediaAsset UUID for hero image"),
    )
    gallery_media_ids = models.JSONField(
        _("gallery media asset IDs"),
        default=list,
        blank=True,
        help_text=_("List of MediaAsset UUIDs for the company gallery"),
    )
    conditions = models.JSONField(
        _("conditions"),
        default=dict,
        blank=True,
        help_text=_("Common conditions: guarantee, insurance, damage_policy, min_age, etc."),
    )
    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    organizer = models.ForeignKey(
        Organizer,
        on_delete=models.CASCADE,
        related_name="car_rental_companies",
        verbose_name=_("organizer"),
        null=True,
        blank=True,
    )
    country = models.CharField(_("country"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("Car rental company")
        verbose_name_plural = _("Car rental companies")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Car(BaseModel):
    """Vehículo individual: precio por día, horarios retiro/devolución, incluido/no incluido."""

    STATUS_CHOICES = [
        ("draft", _("Draft")),
        ("published", _("Published")),
        ("cancelled", _("Cancelled")),
    ]
    TRANSMISSION_CHOICES = [
        ("manual", _("Manual")),
        ("automatic", _("Automatic")),
    ]

    company = models.ForeignKey(
        CarRentalCompany,
        on_delete=models.CASCADE,
        related_name="cars",
        verbose_name=_("company"),
        db_index=True,
    )
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

    price_per_day = models.DecimalField(
        _("price per day"),
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(_("currency"), max_length=3, default="CLP")

    pickup_time_default = models.CharField(
        _("default pickup time"),
        max_length=5,
        blank=True,
        help_text=_("HH:MM"),
    )
    return_time_default = models.CharField(
        _("default return time"),
        max_length=5,
        blank=True,
        help_text=_("HH:MM"),
    )

    included = models.JSONField(
        _("included"),
        default=list,
        blank=True,
        help_text=_("List of what's included"),
    )
    not_included = models.JSONField(
        _("not included"),
        default=list,
        blank=True,
        help_text=_("List of what's not included"),
    )
    inherit_company_conditions = models.BooleanField(
        _("inherit company conditions"),
        default=True,
    )
    conditions_override = models.JSONField(
        _("conditions override"),
        default=dict,
        blank=True,
        help_text=_("Override or complement company conditions when not inheriting"),
    )

    gallery_media_ids = models.JSONField(
        _("gallery media asset IDs"),
        default=list,
        blank=True,
    )
    images = models.JSONField(_("image URLs fallback"), default=list, blank=True)

    min_driver_age = models.PositiveIntegerField(
        _("minimum driver age"),
        null=True,
        blank=True,
        validators=[MinValueValidator(18)],
    )
    transmission = models.CharField(
        _("transmission"),
        max_length=20,
        choices=TRANSMISSION_CHOICES,
        default="manual",
        blank=True,
    )
    seats = models.PositiveIntegerField(
        _("seats"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    bags = models.PositiveIntegerField(
        _("bags"),
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )

    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = _("Car")
        verbose_name_plural = _("Cars")
        ordering = ["company", "title"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.company.name})"


class CarBlockedDate(models.Model):
    """Fecha bloqueada para un auto (no disponible para reserva)."""

    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name="blocked_dates",
        verbose_name=_("car"),
    )
    date = models.DateField(_("date"), db_index=True)

    class Meta:
        verbose_name = _("Car blocked date")
        verbose_name_plural = _("Car blocked dates")
        unique_together = [("car", "date")]
        ordering = ["car", "date"]
        indexes = [
            models.Index(fields=["car", "date"]),
        ]

    def __str__(self):
        return f"{self.car.title} - {self.date}"


class CarReservation(BaseModel):
    """
    Reservation for a car (WhatsApp flow: operator confirms then payment).
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
    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name=_("car"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    pickup_date = models.DateField(_("pickup date"))
    return_date = models.DateField(_("return date"))
    pickup_time = models.CharField(_("pickup time"), max_length=5, blank=True)
    return_time = models.CharField(_("return time"), max_length=5, blank=True)

    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email"))
    phone = models.CharField(_("phone"), max_length=20, blank=True)

    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="car_rental_reservations",
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

    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)

    flow = models.ForeignKey(
        "core.PlatformFlow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="car_rental_reservations",
        verbose_name=_("platform flow"),
        help_text=_("Platform flow tracking this reservation"),
    )

    class Meta:
        verbose_name = _("Car reservation")
        verbose_name_plural = _("Car reservations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["reservation_id"]),
            models.Index(fields=["car", "status"]),
            models.Index(fields=["pickup_date", "return_date"]),
        ]

    def __str__(self):
        return f"{self.reservation_id} - {self.car.title} ({self.status})"
