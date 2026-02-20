"""Models for Erasmus registration and tracking."""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from core.models import TimeStampedModel, BaseModel


class ErasmusLead(TimeStampedModel):
    """
    Registration from the Erasmus landing form.
    Base fields are fixed; extra questions are stored in extra_data.
    Optionally linked to User when they activate an account (e.g. for reservations).
    """

    first_name = models.CharField(_("first name"), max_length=150)
    last_name = models.CharField(_("last name"), max_length=150)
    nickname = models.CharField(_("nickname"), max_length=100, blank=True)
    birth_date = models.DateField(_("birth date"), null=True, blank=True)
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

    arrival_date = models.DateField(_("arrival date"), null=True, blank=True)
    departure_date = models.DateField(_("departure date"), null=True, blank=True)

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

    # Idioma con el que vieron el formulario (selector arriba: Español, English, etc.). Usado para enviar el mensaje de bienvenida por WhatsApp en su idioma.
    form_locale = models.CharField(
        _("form locale"),
        max_length=10,
        blank=True,
        default="es",
        help_text=_("Language the lead used to view the registration form (es, en, pt, de, it, fr). Used for welcome WhatsApp message."),
    )

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

    COMPLETION_STATUS_CHOICES = (
        ("complete", _("Completo")),
        ("pending_completion", _("Por completar")),
    )
    completion_status = models.CharField(
        _("completion status"),
        max_length=30,
        choices=COMPLETION_STATUS_CHOICES,
        default="complete",
        db_index=True,
        help_text=_("Por completar: lead cargado con datos parciales (ej. WhatsApp), falta completar en el formulario"),
    )
    is_suspended = models.BooleanField(
        _("suspended"),
        default=False,
        db_index=True,
        help_text=_("Si está suspendido, no aparece en comunidad y no puede usar enlaces de acceso"),
    )
    requested_whatsapp_approval_at = models.DateTimeField(
        _("requested WhatsApp approval at"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Cuando el lead pulsó 'Confirmar que terminé mi registro' para que el operador lo apruebe en el grupo"),
    )

    # Community directory (Conoce a la comunidad)
    languages_spoken = models.JSONField(
        _("languages spoken"),
        default=list,
        blank=True,
        help_text=_("List of language codes the lead speaks (e.g. es, en, pt)"),
    )
    opt_in_community = models.BooleanField(
        _("opt in community"),
        default=False,
        help_text=_("Lead wants to appear in the public community directory"),
    )
    community_bio = models.TextField(
        _("community bio"),
        blank=True,
        help_text=_("Optional short description for the community card"),
    )
    profile_photo = models.ImageField(
        _("profile photo"),
        upload_to="erasmus_profiles/%Y/%m/",
        blank=True,
        null=True,
        help_text=_("Optional photo for the community card (uploaded after registration)"),
    )
    community_profile_token = models.CharField(
        _("community profile token"),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Token to authorize profile update (photo/bio) from gracias page"),
    )
    community_show_dates = models.BooleanField(
        _("community show dates"),
        default=True,
        help_text=_("Show arrival/departure dates on community profile"),
    )
    community_show_age = models.BooleanField(
        _("community show age"),
        default=True,
        help_text=_("Show age (from birth_date) on community profile"),
    )
    community_show_whatsapp = models.BooleanField(
        _("community show whatsapp"),
        default=False,
        help_text=_("Show WhatsApp on community profile"),
    )

    class Meta:
        verbose_name = _("Erasmus lead")
        verbose_name_plural = _("Erasmus leads")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email or self.phone_number})"


class ErasmusLocalPartner(TimeStampedModel):
    """
    Local partner/team member shown in the gracias page (Meet Your Local Partners).
    Configurable from superadmin. Photo comes from the media library (asset) or legacy ImageField (photo).
    """
    name = models.CharField(_("name"), max_length=150)
    role = models.CharField(_("role"), max_length=150, blank=True, help_text=_("Title/role, e.g. 'Founder & Guide'"))
    photo = models.ImageField(
        _("photo"),
        upload_to="erasmus_partners/%Y/%m/",
        blank=True,
        null=True,
        help_text=_("Legacy: direct upload. Prefer asset from media library."),
    )
    asset = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("photo (from media library)"),
        help_text=_("Profile photo from Biblioteca de Medios."),
    )
    bio = models.TextField(_("bio"), blank=True, help_text=_("Short description (1–2 lines)"))
    instagram_username = models.CharField(
        _("instagram username"),
        max_length=100,
        blank=True,
        help_text=_("Username without @. Link will be instagram.com/{username}"),
    )
    whatsapp_number = models.CharField(
        _("whatsapp number"),
        max_length=30,
        blank=True,
        help_text=_("Full number with country code, e.g. 56912345678. Link: wa.me/{number}"),
    )
    order = models.PositiveIntegerField(_("order"), default=0, db_index=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("Erasmus local partner")
        verbose_name_plural = _("Erasmus local partners")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} ({self.role or 'partner'})"


class ErasmusMagicLink(TimeStampedModel):
    """
    Two-phase magic-link flow — mirrors the WhatsApp reservation code pattern:

    Phase 1 – Verification  (status=pending_whatsapp)
      Frontend generates a code ERAS-XXXXX and shows a wa.me URL with a pre-filled
      message. The user sends it to Tuki's WhatsApp number.

    Phase 2 – Access link delivered  (status=link_sent)
      The WhatsApp bot detects the ERAS-XXXXX code, generates a secure access_token,
      and replies with a personalized welcome message + magic link
      {FRONTEND_URL}/erasmus/acceder?token={access_token}

    Phase 3 – Used  (status=used)
      The student opens the link, gets a JWT, and is redirected to the correct tab.
    """

    STATUS_PENDING = "pending_whatsapp"
    STATUS_LINK_SENT = "link_sent"
    STATUS_USED = "used"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = (
        (STATUS_PENDING, _("Waiting for WhatsApp message")),
        (STATUS_LINK_SENT, _("Magic link sent via WhatsApp")),
        (STATUS_USED, _("Used – student logged in")),
        (STATUS_EXPIRED, _("Expired")),
    )
    TARGET_COMMUNITY = "community"
    TARGET_WHATSAPP = "whatsapp"
    TARGET_CHOICES = (
        (TARGET_COMMUNITY, _("Comunidad Erasmus")),
        (TARGET_WHATSAPP, _("Grupos de WhatsApp")),
    )

    lead = models.ForeignKey(
        "ErasmusLead",
        on_delete=models.CASCADE,
        related_name="magic_links",
        verbose_name=_("Erasmus lead"),
    )
    # Sent by the user via WhatsApp (ERAS-XXXXX format). Unique per code.
    verification_code = models.CharField(
        _("verification code"),
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_("Code embedded in the WhatsApp pre-fill message (e.g. ERAS-A1B2C3)"),
    )
    # Generated after receiving the WhatsApp message; used in the magic link URL.
    access_token = models.CharField(
        _("access token"),
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Secure random token set when WhatsApp message is received"),
    )
    target = models.CharField(_("target"), max_length=20, choices=TARGET_CHOICES)
    status = models.CharField(
        _("status"),
        max_length=25,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    # Expiry of the verification code (Phase 1). After this the user must start again.
    expires_at = models.DateTimeField(_("expires at"))
    # Expiry of the access token (Phase 2), set when link is sent.
    link_expires_at = models.DateTimeField(_("link expires at"), null=True, blank=True)
    used_at = models.DateTimeField(_("used at"), null=True, blank=True)

    class Meta:
        verbose_name = _("Erasmus magic link")
        verbose_name_plural = _("Erasmus magic links")
        ordering = ["-created_at"]

    def __str__(self):
        return f"ErasmusMagicLink [{self.verification_code}] {self.lead} → {self.target} ({self.status})"

    @property
    def is_code_valid(self) -> bool:
        """True while waiting for the user's WhatsApp message and not yet expired."""
        from django.utils import timezone
        return self.status == self.STATUS_PENDING and self.expires_at > timezone.now()

    @property
    def is_link_valid(self) -> bool:
        """True if access_token was generated and the link hasn't expired or been used."""
        from django.utils import timezone
        return (
            self.status == self.STATUS_LINK_SENT
            and self.access_token is not None
            and self.link_expires_at is not None
            and self.link_expires_at > timezone.now()
        )


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


class ErasmusWhatsAppGroup(TimeStampedModel):
    """
    WhatsApp group shown in the Erasmus section (student profile / ASMUS).
    Name + link per group. Managed from superadmin (Erasmus > Grupos WhatsApp).
    """

    name = models.CharField(_("name"), max_length=255, help_text=_("Display name of the group"))
    link = models.URLField(_("link"), max_length=500, help_text=_("WhatsApp group invite URL (e.g. https://chat.whatsapp.com/...)"))
    order = models.PositiveIntegerField(_("order"), default=0, db_index=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("Erasmus WhatsApp group")
        verbose_name_plural = _("Erasmus WhatsApp groups")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name}"


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


class ErasmusSlideConfig(BaseModel):
    """
    Assign a MediaAsset to a named slide in the Erasmus landing hero.
    SuperAdmin manages these from /superadmin/sliders.
    Slide IDs match mock: sunset-manquehue, valpo-concon, san-cristobal-bike.
    """

    slide_id = models.CharField(
        _("slide id"),
        max_length=100,
        unique=True,
        help_text=_("e.g. sunset-manquehue, valpo-concon, san-cristobal-bike"),
    )
    asset = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        related_name="erasmus_slide_configs",
        verbose_name=_("asset"),
        null=True,
        blank=True,
    )
    order = models.PositiveIntegerField(_("order"), default=0)
    caption = models.CharField(
        _("caption"),
        max_length=255,
        blank=True,
        help_text=_("Short legend shown on the slide (e.g. place name)"),
    )

    class Meta:
        verbose_name = _("Erasmus slide config")
        verbose_name_plural = _("Erasmus slide configs")
        ordering = ["order", "slide_id"]

    def __str__(self):
        return f"{self.slide_id} -> {self.asset_id or 'unassigned'}"


class ErasmusRegistroBackgroundSlide(BaseModel):
    """
    Ordered images for the Erasmus registration form background.
    Managed from SuperAdmin (Erasmus > Fondo registro). Shown as cycling/carousel
    behind the form to give an "Erasmus vibe" without covering the form content.
    """

    asset = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        related_name="erasmus_registro_background_slides",
        verbose_name=_("asset"),
        null=True,
        blank=True,
    )
    order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("Erasmus registro background slide")
        verbose_name_plural = _("Erasmus registro background slides")
        ordering = ["order", "id"]

    def __str__(self):
        return f"Registro background #{self.order} -> {self.asset_id or 'sin imagen'}"


class ErasmusTimelineItem(BaseModel):
    """
    One item in the Erasmus landing timeline (group experiences with date/location).
    Can be created from JSON in Superadmin; coexists with frontend mocks.
    Public API returns these so the frontend can merge with mocks.
    """

    title_es = models.CharField(_("title Spanish"), max_length=255)
    title_en = models.CharField(_("title English"), max_length=255, blank=True)
    location = models.CharField(_("location"), max_length=255, blank=True)
    image = models.URLField(_("image URL"), max_length=500, blank=True)
    scheduled_date = models.DateField(_("scheduled date"), null=True, blank=True)
    display_order = models.PositiveIntegerField(_("display order"), default=0)
    experience = models.ForeignKey(
        "experiences.Experience",
        on_delete=models.SET_NULL,
        related_name="erasmus_timeline_items",
        null=True,
        blank=True,
        verbose_name=_("experience"),
    )
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("Erasmus timeline item")
        verbose_name_plural = _("Erasmus timeline items")
        ordering = ["display_order", "scheduled_date", "created_at"]

    def __str__(self):
        return f"{self.title_es} ({self.scheduled_date or 'sin fecha'})"


class ErasmusActivity(BaseModel):
    """
    Erasmus "experience-like" activity (not published outside Erasmus).
    Same structure as Experience: itinerary (with optional start/end time), meeting point,
    what's included / not included, duration. Reusable entity with instances (optional start/end time per date).
    """

    title_es = models.CharField(_("title Spanish"), max_length=255)
    title_en = models.CharField(_("title English"), max_length=255, blank=True)
    slug = models.SlugField(_("slug"), max_length=255, unique=True, db_index=True)
    description_es = models.TextField(_("description Spanish"), blank=True)
    description_en = models.TextField(_("description English"), blank=True)
    short_description_es = models.CharField(_("short description Spanish"), max_length=500, blank=True)
    short_description_en = models.CharField(_("short description English"), max_length=500, blank=True)
    location = models.CharField(
        _("location"),
        max_length=255,
        blank=True,
        help_text=_("Short location label (e.g. city or area)"),
    )
    # Meeting point (same as Experience: location_name / location_address)
    location_name = models.CharField(
        _("meeting point name"),
        max_length=255,
        blank=True,
        help_text=_("Meeting point / place name"),
    )
    location_address = models.TextField(
        _("meeting point address"),
        blank=True,
        help_text=_("Full address for meeting point"),
    )
    duration_minutes = models.PositiveIntegerField(
        _("duration in minutes"),
        null=True,
        blank=True,
        help_text=_("Optional duration (e.g. 120 for 2h)"),
    )
    included = models.JSONField(
        _("included"),
        default=list,
        blank=True,
        help_text=_("List of what's included (same as Experience)"),
    )
    not_included = models.JSONField(
        _("not included"),
        default=list,
        blank=True,
        help_text=_("List of what's not included (same as Experience)"),
    )
    itinerary = models.JSONField(
        _("itinerary"),
        default=list,
        blank=True,
        help_text=_("List of items: time (or start_time/end_time), title, description (same as Experience)"),
    )
    images = models.JSONField(
        _("images"),
        default=list,
        blank=True,
        help_text=_("List of image URLs; images[0] = main image (same convention as Experience)"),
    )
    display_order = models.PositiveIntegerField(_("display order"), default=0, db_index=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    experience = models.ForeignKey(
        "experiences.Experience",
        on_delete=models.SET_NULL,
        related_name="erasmus_activities",
        null=True,
        blank=True,
        verbose_name=_("experience"),
        help_text=_("Optional link to a bookable experience"),
    )

    class Meta:
        verbose_name = _("Erasmus activity")
        verbose_name_plural = _("Erasmus activities")
        ordering = ["display_order", "created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "display_order"]),
        ]

    def __str__(self):
        return f"{self.title_es} ({self.slug})"


class ErasmusActivityInstance(BaseModel):
    """
    When an Erasmus activity is scheduled (exact date or month-only).
    One activity can have many instances (e.g. "clases de bachata" on multiple dates).
    """

    activity = models.ForeignKey(
        ErasmusActivity,
        on_delete=models.CASCADE,
        related_name="instances",
        verbose_name=_("activity"),
    )
    scheduled_date = models.DateField(
        _("scheduled date"),
        null=True,
        blank=True,
        help_text=_("Exact date when set; otherwise use month/year or labels"),
    )
    scheduled_month = models.PositiveSmallIntegerField(
        _("scheduled month"),
        null=True,
        blank=True,
        help_text=_("1-12 for month-only (e.g. March)"),
    )
    scheduled_year = models.IntegerField(
        _("scheduled year"),
        null=True,
        blank=True,
        help_text=_("Year for month-only scheduling"),
    )
    scheduled_label_es = models.CharField(
        _("scheduled label Spanish"),
        max_length=100,
        blank=True,
        help_text=_("e.g. Marzo 2026"),
    )
    scheduled_label_en = models.CharField(
        _("scheduled label English"),
        max_length=100,
        blank=True,
        help_text=_("e.g. March 2026"),
    )
    start_time = models.TimeField(
        _("start time"),
        null=True,
        blank=True,
        help_text=_("Optional start time for this instance (HH:MM)"),
    )
    end_time = models.TimeField(
        _("end time"),
        null=True,
        blank=True,
        help_text=_("Optional end time for this instance (HH:MM)"),
    )
    display_order = models.PositiveIntegerField(_("display order"), default=0)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("Erasmus activity instance")
        verbose_name_plural = _("Erasmus activity instances")
        ordering = ["display_order", "scheduled_date", "scheduled_year", "scheduled_month", "created_at"]
        indexes = [
            models.Index(fields=["activity", "scheduled_date"]),
            models.Index(fields=["is_active"]),
        ]

    def clean(self):
        super().clean()
        has_date = bool(self.scheduled_date)
        has_month_year = self.scheduled_month is not None or self.scheduled_year is not None
        has_labels = bool(self.scheduled_label_es or self.scheduled_label_en)
        if not (has_date or has_month_year or has_labels):
            raise ValidationError(
                _("Set either scheduled_date, or scheduled_month/scheduled_year, or scheduled_label_es/en.")
            )
        if self.scheduled_month is not None and (self.scheduled_month < 1 or self.scheduled_month > 12):
            raise ValidationError(_("scheduled_month must be between 1 and 12."))

    def __str__(self):
        if self.scheduled_date:
            return f"{self.activity.title_es} - {self.scheduled_date}"
        label = self.scheduled_label_es or (
            f"{self.scheduled_month or '?'}/{self.scheduled_year or '?'}" if self.scheduled_month else "sin fecha"
        )
        return f"{self.activity.title_es} - {label}"
