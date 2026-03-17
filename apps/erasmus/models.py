"""Models for Erasmus registration and tracking."""

import calendar
from datetime import date

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator

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

    budget_stay = models.CharField(
        _("budget during stay"),
        max_length=200,
        blank=True,
        help_text=_("Presupuesto aproximado durante el intercambio (estancia, paseos, etc.)"),
    )

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

    CATEGORY_UNIVERSITY = "university"
    CATEGORY_TUKI = "tuki"
    CATEGORY_CHOICES = [
        (CATEGORY_UNIVERSITY, _("University groups")),
        (CATEGORY_TUKI, _("Tuki groups")),
    ]

    name = models.CharField(_("name"), max_length=255, help_text=_("Display name of the group"))
    link = models.URLField(_("link"), max_length=500, help_text=_("WhatsApp group invite URL (e.g. https://chat.whatsapp.com/...)"))
    image_url = models.URLField(
        _("image URL"),
        max_length=500,
        blank=True,
        help_text=_("Optional: image to show for the group (e.g. group photo)."),
    )
    category = models.CharField(
        _("category"),
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_TUKI,
        db_index=True,
        help_text=_("University groups vs Tuki groups for display sections."),
    )
    order = models.PositiveIntegerField(_("order"), default=0, db_index=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("Erasmus WhatsApp group")
        verbose_name_plural = _("Erasmus WhatsApp groups")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name}"


class ErasmusPartnerNotificationConfig(TimeStampedModel):
    """
    Config for sending Erasmus event notifications to a WhatsApp group (e.g. Rumi housing).
    One row per notification type (slug). Scalable for future activity-inscription notifications.
    """

    slug = models.SlugField(
        _("slug"),
        max_length=80,
        unique=True,
        db_index=True,
        help_text=_("Identifier for this notification type (e.g. rumi_housing)"),
    )
    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("Display name (e.g. Rumi – Housing)"),
    )
    whatsapp_chat = models.ForeignKey(
        "whatsapp.WhatsAppChat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("WhatsApp group"),
        help_text=_("Group to receive notifications; must be type=group."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        db_index=True,
        help_text=_("If disabled, no notifications are sent."),
    )
    description = models.TextField(
        _("description"),
        blank=True,
        help_text=_("Optional: what events trigger this notification."),
    )

    class Meta:
        verbose_name = _("Erasmus partner notification config")
        verbose_name_plural = _("Erasmus partner notification configs")
        ordering = ["slug"]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class ErasmusActivityNotificationConfig(TimeStampedModel):
    """
    When a lead expresses interest in an Erasmus activity (any instance), send a WhatsApp
    notification to this group. One row per (activity, group). Message includes new person + total inscribed for that instance.
    """

    activity = models.ForeignKey(
        "ErasmusActivity",
        on_delete=models.CASCADE,
        related_name="notification_configs",
        verbose_name=_("Erasmus activity"),
    )
    whatsapp_chat = models.ForeignKey(
        "whatsapp.WhatsAppChat",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("WhatsApp group"),
        help_text=_("Group to receive notifications; must be type=group."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        db_index=True,
    )

    class Meta:
        verbose_name = _("Erasmus activity notification config")
        verbose_name_plural = _("Erasmus activity notification configs")
        ordering = ["activity__display_order", "activity__title_es"]
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "whatsapp_chat"],
                name="erasmus_activity_notif_config_activity_chat_unique",
            ),
        ]

    def __str__(self):
        return f"{self.activity.title_es} → {self.whatsapp_chat.name}"


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


class ErasmusWelcomeMessageConfig(TimeStampedModel):
    """
    Singleton config for WhatsApp welcome message templates per locale (es, en, pt, de, it, fr).
    Editable from Super Admin. Placeholders: {first_name}, {link_plataforma}, {magic_link_url}, {email}.
    If a locale is missing or empty, the code falls back to the default hardcoded template.
    """

    # Single row: we use a constant key so there is only one config record
    CONFIG_KEY = "default"

    config_key = models.CharField(
        _("config key"),
        max_length=50,
        unique=True,
        default=CONFIG_KEY,
        editable=False,
    )
    messages_by_locale = models.JSONField(
        _("messages by locale"),
        default=dict,
        blank=True,
        help_text=_('Dict locale -> template text, e.g. {"es": "Hola {first_name}...", "en": "Hi {first_name}..."}. Placeholders: first_name, link_plataforma, magic_link_url, email.'),
    )

    class Meta:
        verbose_name = _("Erasmus welcome message config")
        verbose_name_plural = _("Erasmus welcome message configs")

    def __str__(self):
        return f"Welcome messages ({len(self.messages_by_locale)} locales)"


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
    DETAIL_LAYOUT_DEFAULT = "default"
    DETAIL_LAYOUT_TWO_COLUMN = "two_column"
    DETAIL_LAYOUT_CHOICES = [
        (DETAIL_LAYOUT_DEFAULT, _("Default (single column, gallery on top)")),
        (DETAIL_LAYOUT_TWO_COLUMN, _("Two columns (photos on one side, info on the other)")),
    ]
    detail_layout = models.CharField(
        _("detail page layout"),
        max_length=20,
        choices=DETAIL_LAYOUT_CHOICES,
        default=DETAIL_LAYOUT_DEFAULT,
        help_text=_("Template for the activity detail page on desktop."),
    )
    experience = models.ForeignKey(
        "experiences.Experience",
        on_delete=models.SET_NULL,
        related_name="erasmus_activities",
        null=True,
        blank=True,
        verbose_name=_("experience"),
        help_text=_("Optional link to a bookable experience"),
    )
    # Actividad de pago: si True, los inscritos pueden ser marcados como pagados (desde lista invitados).
    is_paid = models.BooleanField(
        _("paid activity"),
        default=False,
        db_index=True,
        help_text=_("If set, inscriptions can be marked as paid from the inscritos view; revenue is tracked."),
    )
    # Precio sugerido por inscripción (opcional; se puede sobrescribir al marcar como pagado).
    price = models.DecimalField(
        _("price"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Suggested price per inscription (e.g. for prefilling when marking as paid)."),
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


class ErasmusActivityExtraField(models.Model):
    """
    Dynamic extra question for inscription in a specific Erasmus activity (e.g. número de ruta, pasaporte).
    Configurable per activity in Superadmin; answers are stored in ErasmusActivityInstanceRegistration.extra_data.
    Used in WhatsApp/post-purchase messages as metatags: {{field_key}}.
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

    activity = models.ForeignKey(
        ErasmusActivity,
        on_delete=models.CASCADE,
        related_name="extra_fields",
        verbose_name=_("activity"),
    )
    label = models.CharField(_("label"), max_length=255)
    field_key = models.SlugField(
        _("field key"),
        max_length=80,
        help_text=_("Unique key for this field (e.g. numero_ruta, pasaporte). Use in messages as {{field_key}}."),
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
        verbose_name = _("Erasmus activity extra field")
        verbose_name_plural = _("Erasmus activity extra fields")
        ordering = ["order", "id"]
        unique_together = [("activity", "field_key")]

    def __str__(self):
        return f"{self.activity.title_es} – {self.label} ({self.field_key})"


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
    # Cupos: null = ilimitado. Si no null, no se aceptan más inscripciones cuando inscritos >= capacity.
    capacity = models.PositiveIntegerField(
        _("capacity"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Max participants; leave empty for unlimited."),
    )
    # Control inventario: si True, no se aceptan más inscripciones aunque haya cupo.
    is_agotado = models.BooleanField(
        _("sold out"),
        default=False,
        db_index=True,
        help_text=_("If set, no new sign-ups are accepted."),
    )
    # Instrucciones que se muestran en la página de detalle de esta instancia.
    instructions_es = models.TextField(
        _("instructions Spanish"),
        blank=True,
        help_text=_("Instructions shown in activity details (Spanish)."),
    )
    instructions_en = models.TextField(
        _("instructions English"),
        blank=True,
        help_text=_("Instructions shown in activity details (English)."),
    )
    # Mensaje que se envía por WhatsApp al lead tras inscribirse en esta instancia.
    whatsapp_message_es = models.TextField(
        _("WhatsApp message Spanish"),
        blank=True,
        help_text=_("Message sent by WhatsApp to the lead after they register (Spanish)."),
    )
    whatsapp_message_en = models.TextField(
        _("WhatsApp message English"),
        blank=True,
        help_text=_("Message sent by WhatsApp to the lead after they register (English)."),
    )
    # Mensaje post-pago: correo de confirmación y/o WhatsApp tras pagar. Placeholders: {{first_name}}, {{activity_title}}, {{instance_label}}, {{order_number}}.
    post_purchase_message_es = models.TextField(
        _("Post-purchase message Spanish"),
        blank=True,
        help_text=_("Message in confirmation email and optional WhatsApp after payment (Spanish). Same placeholders as WhatsApp message."),
    )
    post_purchase_message_en = models.TextField(
        _("Post-purchase message English"),
        blank=True,
        help_text=_("Message in confirmation email and optional WhatsApp after payment (English). Same placeholders as WhatsApp message."),
    )
    # Número extra que se suma a los inscritos reales para mostrar (tracción / prueba social).
    interested_count_boost = models.PositiveIntegerField(
        _("interested count boost"),
        default=0,
        help_text=_("Extra number added to real inscritos count for display (social proof)."),
    )

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

    @property
    def is_past(self):
        """True if this instance date is in the past (no more sign-ups)."""
        today = timezone.now().date()
        if self.scheduled_date is not None:
            return self.scheduled_date < today
        if self.scheduled_year is not None and self.scheduled_month is not None:
            try:
                _, last_day = calendar.monthrange(self.scheduled_year, self.scheduled_month)
                end_of_month = date(self.scheduled_year, self.scheduled_month, last_day)
                return end_of_month < today
            except (ValueError, TypeError):
                pass
        return False

    def __str__(self):
        if self.scheduled_date:
            return f"{self.activity.title_es} - {self.scheduled_date}"
        label = self.scheduled_label_es or (
            f"{self.scheduled_month or '?'}/{self.scheduled_year or '?'}" if self.scheduled_month else "sin fecha"
        )
        return f"{self.activity.title_es} - {label}"


class ErasmusActivityInstanceRegistration(TimeStampedModel):
    """
    One registration of a lead for an activity instance, with optional extra_data (answers to
    ErasmusActivityExtraField). Used for CSV export and for message metatags ({{field_key}}).
    """
    lead = models.ForeignKey(
        ErasmusLead,
        on_delete=models.CASCADE,
        related_name="activity_instance_registrations",
        verbose_name=_("lead"),
    )
    instance = models.ForeignKey(
        ErasmusActivityInstance,
        on_delete=models.CASCADE,
        related_name="registrations",
        verbose_name=_("instance"),
    )
    extra_data = models.JSONField(
        _("extra data"),
        default=dict,
        blank=True,
        help_text=_("Answers to activity extra fields: {field_key: value}."),
    )

    class Meta:
        verbose_name = _("Erasmus activity instance registration")
        verbose_name_plural = _("Erasmus activity instance registrations")
        unique_together = [("lead", "instance")]

    def __str__(self):
        return f"{self.lead} – {self.instance}"


class ErasmusActivityPublicLink(models.Model):
    """
    Public links for an Erasmus activity: one to view inscritos (list), one to edit (full UI).
    Tokens in URL; no login. links_enabled toggles both links on/off.
    """

    activity = models.OneToOneField(
        ErasmusActivity,
        on_delete=models.CASCADE,
        related_name="public_link",
        verbose_name=_("activity"),
    )
    view_token = models.CharField(
        _("view token"),
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("Token for public view link (list of inscritos)."),
    )
    edit_token = models.CharField(
        _("edit token"),
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("Token for public edit link (same UI as superadmin, no auth)."),
    )
    review_token = models.CharField(
        _("review token"),
        max_length=64,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        help_text=_("Token for public review link (students leave a review for an instance)."),
    )
    links_enabled = models.BooleanField(
        _("links enabled"),
        default=True,
        db_index=True,
        help_text=_("When False, both public links return disabled/404."),
    )
    review_link_enabled = models.BooleanField(
        _("review link enabled"),
        default=True,
        db_index=True,
        help_text=_("When False, the review link returns disabled/404 (stops new reviews)."),
    )

    class Meta:
        verbose_name = _("Erasmus activity public link")
        verbose_name_plural = _("Erasmus activity public links")

    def __str__(self):
        return f"{self.activity.title_es} (view/edit/review)"


# Formas de pago al marcar inscripción como pagada (manual o pago en línea).
PAYMENT_METHOD_CHOICES = [
    ("platform", _("Pago en línea (plataforma)")),
    ("efectivo", _("Efectivo")),
    ("transferencia", _("Transferencia")),
    ("tarjeta", _("Tarjeta")),
    ("mercadopago", _("Mercado Pago")),
    ("paypal", _("PayPal")),
    ("other", _("Otro")),
]


class ErasmusActivityInscriptionPayment(TimeStampedModel):
    """
    Pago registrado manualmente para una inscripción en una instancia de actividad Erasmus.
    Quien tiene el link de invitados puede marcar como pagado; se selecciona forma de pago.
    Estos ingresos se contabilizan en el revenue de Tuki (superadmin sales analytics).
    """
    lead = models.ForeignKey(
        ErasmusLead,
        on_delete=models.CASCADE,
        related_name="activity_inscription_payments",
        verbose_name=_("lead"),
    )
    instance = models.ForeignKey(
        ErasmusActivityInstance,
        on_delete=models.CASCADE,
        related_name="inscription_payments",
        verbose_name=_("activity instance"),
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        help_text=_("Amount paid for this inscription."),
    )
    payment_method = models.CharField(
        _("payment method"),
        max_length=32,
        choices=PAYMENT_METHOD_CHOICES,
        default="efectivo",
    )
    paid_at = models.DateTimeField(
        _("paid at"),
        default=timezone.now,
        help_text=_("When the payment was recorded."),
    )
    # Exclude from revenue (cortesía, invitados, prueba) — do not count in erasmus_sales
    exclude_from_revenue = models.BooleanField(
        _("exclude from revenue"),
        default=False,
        db_index=True,
        help_text=_("If True, this payment does not count in revenue (cortesía, invited guests, test)."),
    )

    class Meta:
        verbose_name = _("Erasmus activity inscription payment")
        verbose_name_plural = _("Erasmus activity inscription payments")
        ordering = ["-paid_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["lead", "instance"],
                name="erasmus_inscription_payment_unique_lead_instance",
            )
        ]
        indexes = [
            models.Index(fields=["instance"]),
        ]

    def __str__(self):
        return f"{self.lead} – {self.instance} – {self.amount} ({self.payment_method})"


class ErasmusActivityPaymentLink(models.Model):
    """
    Link de pago para una inscripción en actividad Erasmus (pago en línea).
    Order (order_kind=erasmus_activity) se vincula aquí; al confirmar pago se crea
    ErasmusActivityInscriptionPayment con payment_method='platform'.
    """
    lead = models.ForeignKey(
        ErasmusLead,
        on_delete=models.CASCADE,
        related_name="activity_payment_links",
        verbose_name=_("lead"),
    )
    instance = models.ForeignKey(
        ErasmusActivityInstance,
        on_delete=models.CASCADE,
        related_name="payment_links",
        verbose_name=_("activity instance"),
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        help_text=_("Amount to pay for this inscription."),
    )
    currency = models.CharField(_("currency"), max_length=3, default="CLP")
    token = models.CharField(
        _("token"),
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("URL-safe token for the payment link."),
    )
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    # Estado de envío del link por WhatsApp (automático al inscribirse, o manual si se copia y manda)
    link_sent_at = models.DateTimeField(
        _("link sent at"),
        null=True,
        blank=True,
        help_text=_("When the payment link was sent to the lead (WhatsApp)."),
    )
    link_sent_via = models.CharField(
        _("link sent via"),
        max_length=20,
        choices=[
            ("automatic", _("Automático")),
            ("manual", _("Manual")),
        ],
        null=True,
        blank=True,
        help_text=_("Whether the link was sent automatically (flow) or marked as sent manually."),
    )
    link_send_error = models.CharField(
        _("link send error"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Error message if automatic send failed (e.g. WhatsApp disconnected)."),
    )

    class Meta:
        verbose_name = _("Erasmus activity payment link")
        verbose_name_plural = _("Erasmus activity payment links")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["instance"])]
        constraints = [
            models.UniqueConstraint(
                fields=("lead", "instance"),
                name="erasmus_activity_payment_link_lead_instance_unique",
            ),
        ]

    def __str__(self):
        return f"{self.lead} – {self.instance} – {self.amount}"


class ErasmusActivityReview(TimeStampedModel):
    """
    Review left by a student for a specific instance of an Erasmus activity.
    Created via the public review link (review_token). Always tied to an instance (fecha).
    Displayed on the activity detail page and in superadmin per instance.
    """

    instance = models.ForeignKey(
        ErasmusActivityInstance,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("instance"),
        help_text=_("The activity instance (date) this review is for."),
    )
    author_name = models.CharField(
        _("author name"),
        max_length=255,
        help_text=_("Name shown with the review (e.g. from Erasmus profile or form)."),
    )
    author_origin = models.CharField(
        _("author origin"),
        max_length=255,
        blank=True,
        help_text=_("Where they are from (e.g. country/city)."),
    )
    rating = models.PositiveSmallIntegerField(
        _("rating"),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_("1-5 stars satisfaction."),
    )
    body = models.TextField(
        _("body"),
        help_text=_("Review text / comment."),
    )
    lead = models.ForeignKey(
        ErasmusLead,
        on_delete=models.SET_NULL,
        related_name="activity_reviews",
        verbose_name=_("lead"),
        null=True,
        blank=True,
        help_text=_("Optional link to Erasmus lead if identified (e.g. from magic link)."),
    )

    class Meta:
        verbose_name = _("Erasmus activity review")
        verbose_name_plural = _("Erasmus activity reviews")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["instance"]),
        ]

    def __str__(self):
        return f"{self.author_name} – {self.rating}★ for {self.instance}"


# -----------------------------------------------------------------------------
# Contests / Sorteos (landing + inscripción + código WhatsApp + flujo)
# -----------------------------------------------------------------------------


class Contest(TimeStampedModel):
    """
    Sorteo/concurso con landing pública: slider, experiencia vinculada,
    T&C, requisitos (pasos a seguir), formulario con preguntas dinámicas.
    Inscripción genera código WhatsApp y flujo (PlatformFlow).
    """

    slug = models.SlugField(
        _("slug"),
        max_length=120,
        unique=True,
        help_text=_("URL identifier, e.g. salar-uyuni-2026"),
    )
    title = models.CharField(_("title"), max_length=255)
    subtitle = models.CharField(_("subtitle"), max_length=255, blank=True)
    headline = models.TextField(
        _("headline"),
        blank=True,
        help_text=_("Main message e.g. 'Tuki y House and Flats te regalan un viaje para dos...'"),
    )
    experience = models.ForeignKey(
        "experiences.Experience",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contests",
        verbose_name=_("experience"),
    )
    terms_and_conditions_html = models.TextField(
        _("terms and conditions HTML"),
        blank=True,
        help_text=_("Rich text (HTML) for T&C page"),
    )
    requirements_html = models.TextField(
        _("requirements HTML"),
        blank=True,
        help_text=_("Requisitos / pasos a seguir (rich text), shown on landing"),
    )
    # WhatsApp: mensaje que recibe el participante al enviar su código (placeholders: {{nombre}}, {{codigo}}, {{concurso}})
    whatsapp_confirmation_message = models.TextField(
        _("WhatsApp confirmation message"),
        blank=True,
        help_text=_(
            "Message sent back when participant sends their code via WhatsApp. "
            "Placeholders: {{nombre}}, {{codigo}}, {{concurso}}."
        ),
    )
    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    starts_at = models.DateTimeField(_("starts at"), null=True, blank=True)
    ends_at = models.DateTimeField(_("ends at"), null=True, blank=True)
    order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("Contest")
        verbose_name_plural = _("Contests")
        ordering = ["order", "slug"]

    def __str__(self):
        return f"{self.title} ({self.slug})"


class ContestSlideConfig(BaseModel):
    """Slide del hero del concurso; imágenes desde biblioteca de medios."""

    contest = models.ForeignKey(
        Contest,
        on_delete=models.CASCADE,
        related_name="slide_configs",
        verbose_name=_("contest"),
    )
    asset = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        related_name="contest_slide_configs",
        verbose_name=_("asset"),
        null=True,
        blank=True,
    )
    order = models.PositiveIntegerField(_("order"), default=0)
    caption = models.CharField(_("caption"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("Contest slide config")
        verbose_name_plural = _("Contest slide configs")
        ordering = ["contest", "order", "id"]

    def __str__(self):
        return f"{self.contest.slug} slide #{self.order} -> {self.asset_id or 'unassigned'}"


class ContestExtraField(models.Model):
    """Pregunta dinámica del formulario de inscripción del concurso."""

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

    contest = models.ForeignKey(
        Contest,
        on_delete=models.CASCADE,
        related_name="extra_fields",
        verbose_name=_("contest"),
    )
    label = models.CharField(_("label"), max_length=255)
    field_key = models.SlugField(_("field key"), max_length=80)
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
        verbose_name = _("Contest extra field")
        verbose_name_plural = _("Contest extra fields")
        ordering = ["contest", "order", "id"]
        unique_together = [["contest", "field_key"]]

    def __str__(self):
        return f"{self.contest.slug}: {self.label} ({self.field_key})"


class ContestRegistration(TimeStampedModel):
    """Inscripción a un concurso; vinculada a un flujo (PlatformFlow) y opcionalmente a un código WhatsApp."""

    contest = models.ForeignKey(
        Contest,
        on_delete=models.CASCADE,
        related_name="registrations",
        verbose_name=_("contest"),
    )
    first_name = models.CharField(_("first name"), max_length=150)
    last_name = models.CharField(_("last name"), max_length=150)
    email = models.EmailField(_("email"), blank=True, null=True)
    phone_country_code = models.CharField(_("phone country code"), max_length=10, blank=True)
    phone_number = models.CharField(_("phone number"), max_length=20, blank=True)
    extra_data = models.JSONField(
        _("extra data"),
        default=dict,
        blank=True,
        help_text=_("Answers to ContestExtraField questions"),
    )
    accept_terms = models.BooleanField(_("accept terms"), default=False)
    flow = models.ForeignKey(
        "core.PlatformFlow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contest_registrations",
        verbose_name=_("flow"),
    )

    class Meta:
        verbose_name = _("Contest registration")
        verbose_name_plural = _("Contest registrations")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["contest", "created_at"])]

    def __str__(self):
        return f"{self.first_name} {self.last_name} – {self.contest.slug}"


class ContestParticipationCode(TimeStampedModel):
    """
    Código único para confirmar participación por WhatsApp (como reservas).
    Se genera al inscribirse; el usuario envía el código por WhatsApp y recibe
    el mensaje personalizado del concurso (whatsapp_confirmation_message).
    """

    STATUS_CHOICES = [
        ("pending", _("Pendiente")),
        ("confirmed", _("Confirmado")),
    ]

    contest = models.ForeignKey(
        Contest,
        on_delete=models.CASCADE,
        related_name="participation_codes",
        verbose_name=_("contest"),
    )
    registration = models.OneToOneField(
        ContestRegistration,
        on_delete=models.CASCADE,
        related_name="participation_code",
        verbose_name=_("registration"),
    )
    code = models.CharField(_("code"), max_length=50, unique=True, db_index=True)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    flow = models.ForeignKey(
        "core.PlatformFlow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contest_participation_codes",
        verbose_name=_("flow"),
    )

    class Meta:
        verbose_name = _("Contest participation code")
        verbose_name_plural = _("Contest participation codes")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} – {self.contest.slug}"
