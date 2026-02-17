"""Models for Erasmus registration and tracking."""

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from core.models import TimeStampedModel


class ErasmusLead(TimeStampedModel):
    """
    Registration from the Erasmus landing form.
    Base fields are fixed; extra questions are stored in extra_data.
    Optionally linked to User when they activate an account (e.g. for reservations).
    """

    first_name = models.CharField(_("first name"), max_length=150)
    last_name = models.CharField(_("last name"), max_length=150)
    nickname = models.CharField(_("nickname"), max_length=100, blank=True)
    birth_date = models.DateField(_("birth date"))
    country = models.CharField(
        _("country"),
        max_length=100,
        blank=True,
        help_text=_("Country of origin or residence (país)"),
    )
    city = models.CharField(
        _("city"),
        max_length=150,
        blank=True,
        help_text=_("City of origin or residence (ciudad)"),
    )
    email = models.EmailField(_("email"), blank=True, null=True)
    phone_country_code = models.CharField(_("phone country code"), max_length=10)
    phone_number = models.CharField(_("phone number"), max_length=20)
    instagram = models.CharField(_("instagram"), max_length=100, blank=True)

    STAY_REASON_CHOICES = (
        ("university", _("Intercambio / Erasmus (universidad)")),
        ("practicas", _("Prácticas / Internship")),
        ("other", _("Otro")),
    )
    stay_reason = models.CharField(
        _("reason for stay"),
        max_length=20,
        choices=STAY_REASON_CHOICES,
        help_text=_("Qué viene a hacer: universidad, prácticas u otro"),
    )
    stay_reason_detail = models.CharField(
        _("reason detail"),
        max_length=500,
        blank=True,
        help_text=_("Ej. dónde hará prácticas o descripción si eligió otro"),
    )
    university = models.CharField(_("university"), max_length=255, blank=True)
    degree = models.CharField(_("degree / career"), max_length=255, blank=True)

    arrival_date = models.DateField(_("arrival date"))
    departure_date = models.DateField(_("departure date"))

    has_accommodation_in_chile = models.BooleanField(
        _("has accommodation in Chile"),
        default=False,
        help_text=_("Si ya tiene alojamiento en Chile"),
    )
    wants_rumi4students_contact = models.BooleanField(
        _("wants Rumi4Students contact"),
        default=False,
        help_text=_("Quiere que lo contactemos para ayudarle a encontrar alojamiento con agencias partner Rumi4Students"),
    )

    destinations = models.JSONField(
        _("destinations"),
        default=list,
        help_text=_("List of destination/experience slugs selected"),
    )
    interested_experiences = models.JSONField(
        _("interested experiences"),
        default=list,
        blank=True,
        help_text=_("List of Erasmus timeline experience IDs the lead is interested in"),
    )
    interests = models.JSONField(
        _("interests"),
        default=list,
        help_text=_("List of interest slugs/ids selected"),
    )

    source_slug = models.CharField(
        _("source slug"),
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text=_("Tracking link identifier (e.g. from ?source=maria_ig)"),
    )
    utm_source = models.CharField(_("utm source"), max_length=255, blank=True, null=True)
    utm_medium = models.CharField(_("utm medium"), max_length=255, blank=True, null=True)
    utm_campaign = models.CharField(_("utm campaign"), max_length=255, blank=True, null=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erasmus_leads",
        verbose_name=_("user"),
        help_text=_("Linked when account is created (e.g. from email)"),
    )
    extra_data = models.JSONField(
        _("extra data"),
        default=dict,
        blank=True,
        help_text=_("Answers to dynamic extra questions (ErasmusExtraField)"),
    )

    # Consent (T&C Especiales Registro Erasmus)
    accept_tc_erasmus = models.BooleanField(
        _("accept TC Erasmus"),
        default=False,
        help_text=_("Usuario acepta T&C Especiales del Registro Erasmus"),
    )
    accept_privacy_erasmus = models.BooleanField(
        _("accept privacy Erasmus"),
        default=False,
        help_text=_("Usuario declara haber leído Política de Privacidad y addendum Erasmus"),
    )
    consent_email = models.BooleanField(
        _("consent email"),
        default=False,
        help_text=_("Consentimiento para recibir recomendaciones por email"),
    )
    consent_whatsapp = models.BooleanField(
        _("consent WhatsApp"),
        default=False,
        help_text=_("Consentimiento para recibir recomendaciones por WhatsApp"),
    )
    consent_share_providers = models.BooleanField(
        _("consent share providers"),
        default=False,
        help_text=_("Autorización para compartir datos mínimos con proveedores al solicitar cotización/reserva"),
    )

    class Meta:
        verbose_name = _("Erasmus lead")
        verbose_name_plural = _("Erasmus leads")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email or self.phone_number})"


class ErasmusDestinationGuide(TimeStampedModel):
    """
    Guía de viaje asociada a un destino. Configurable desde superadmin.
    Por cada destino que el lead seleccione, recibirá las guías asignadas
    (en su perfil y por WhatsApp).
    """
    destination_slug = models.CharField(
        _("destination slug"),
        max_length=120,
        db_index=True,
        help_text=_("Slug del destino (ej. san-pedro-atacama, torres-del-paine)"),
    )
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    file_url = models.URLField(
        _("file URL"),
        max_length=500,
        blank=True,
        help_text=_("URL del PDF o recurso de la guía"),
    )
    order = models.PositiveIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("Erasmus destination guide")
        verbose_name_plural = _("Erasmus destination guides")
        ordering = ["destination_slug", "order", "id"]

    def __str__(self):
        return f"{self.title} ({self.destination_slug})"


class ErasmusTrackingLink(models.Model):
    """
    Tracking links for the team to measure acquisition source.
    URL format: /erasmus/registro?source=<slug>
    """

    name = models.CharField(_("name"), max_length=255, help_text=_("e.g. Instagram María"))
    slug = models.SlugField(_("slug"), max_length=100, unique=True, db_index=True)

    class Meta:
        verbose_name = _("Erasmus tracking link")
        verbose_name_plural = _("Erasmus tracking links")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class ErasmusExtraField(models.Model):
    """
    Dynamic extra question for the Erasmus registration form (like FormField).
    Base fields (name, phone, country, etc.) are fixed; these are configurable by superadmin.
    """

    FIELD_TYPE_CHOICES = (
        ("text", _("Text")),
        ("email", _("Email")),
        ("phone", _("Phone")),
        ("number", _("Number")),
        ("select", _("Select")),
        ("multiselect", _("Multiple select")),
        ("checkbox", _("Checkbox")),
        ("radio", _("Radio")),
        ("date", _("Date")),
        ("textarea", _("Text area")),
        ("url", _("URL")),
    )

    label = models.CharField(_("label"), max_length=255)
    field_key = models.SlugField(
        _("field key"),
        max_length=80,
        unique=True,
        help_text=_("Unique key for this field (e.g. motivacion_erasmus)"),
    )
    type = models.CharField(_("type"), max_length=20, choices=FIELD_TYPE_CHOICES)
    required = models.BooleanField(_("required"), default=False)
    placeholder = models.CharField(_("placeholder"), max_length=255, blank=True)
    help_text = models.TextField(_("help text"), blank=True)
    order = models.PositiveIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    options = models.JSONField(
        _("options"),
        default=list,
        blank=True,
        help_text=_("For select/radio: list of {value, label}"),
    )

    class Meta:
        verbose_name = _("Erasmus extra field")
        verbose_name_plural = _("Erasmus extra fields")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.label} ({self.field_key})"
