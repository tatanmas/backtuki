"""Models for landing destinations (Tuki main site destination pages)."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel


class LandingDestination(BaseModel):
    """
    Destination for the main Tuki landing (e.g. Valparaíso, Cochamó).
    Configurable via superadmin: photos, guides, experiences, accommodations, featured item.
    """

    name = models.CharField(_("name"), max_length=255, db_index=True)
    slug = models.SlugField(_("slug"), max_length=255, unique=True, db_index=True)
    country = models.CharField(_("country"), max_length=255, default="Chile")
    region = models.CharField(_("region"), max_length=255, blank=True)
    description = models.TextField(_("description"), blank=True)
    hero_image = models.URLField(_("hero image URL fallback"), max_length=500, blank=True)
    hero_media_id = models.UUIDField(_("hero image from media library"), null=True, blank=True)
    gallery_media_ids = models.JSONField(
        _("gallery image IDs from media library"),
        default=list,
        help_text=_("List of MediaAsset UUIDs for the destination gallery"),
    )
    latitude = models.FloatField(_("latitude"), null=True, blank=True)
    longitude = models.FloatField(_("longitude"), null=True, blank=True)
    temperature = models.IntegerField(_("temperature (cached)"), null=True, blank=True)
    local_time = models.CharField(_("local time (cached)"), max_length=50, blank=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    # Legacy/fallback: raw URLs if not using media library
    images = models.JSONField(
        _("gallery image URLs fallback"),
        default=list,
        help_text=_("List of image URLs when not using gallery_media_ids"),
    )
    travel_guides = models.JSONField(
        _("travel guides"),
        default=list,
        help_text=_("List of {id, title, image, description?, author?}"),
    )
    transportation = models.JSONField(
        _("transportation options"),
        default=list,
        help_text=_("List of {id, type, icon, title, description, price?}"),
    )
    accommodation_ids = models.JSONField(
        _("accommodation IDs"),
        default=list,
        help_text=_("List of accommodation UUIDs (for when accommodations app is populated)"),
    )

    # Featured block: experience, event, or accommodation
    FEATURED_TYPE_CHOICES = [
        ("experience", _("Experience")),
        ("event", _("Event")),
        ("accommodation", _("Accommodation")),
    ]
    featured_type = models.CharField(
        _("featured type"),
        max_length=20,
        choices=FEATURED_TYPE_CHOICES,
        blank=True,
        null=True,
    )
    featured_id = models.UUIDField(_("featured entity ID"), null=True, blank=True)

    class Meta:
        verbose_name = _("Landing Destination")
        verbose_name_plural = _("Landing Destinations")
        ordering = ["name"]

    def __str__(self):
        return self.name


class LandingDestinationExperience(models.Model):
    """M2M through model: which experiences are shown for a landing destination."""

    destination = models.ForeignKey(
        LandingDestination,
        on_delete=models.CASCADE,
        related_name="destination_experiences",
    )
    experience_id = models.UUIDField(_("experience ID"), db_index=True)
    order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["order", "experience_id"]
        unique_together = [["destination", "experience_id"]]
        verbose_name = _("Landing destination experience")
        verbose_name_plural = _("Landing destination experiences")


class LandingDestinationEvent(models.Model):
    """M2M through model: which events are shown for a landing destination."""

    destination = models.ForeignKey(
        LandingDestination,
        on_delete=models.CASCADE,
        related_name="destination_events",
    )
    event_id = models.UUIDField(_("event ID"), db_index=True)
    order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["order", "event_id"]
        unique_together = [["destination", "event_id"]]
        verbose_name = _("Landing destination event")
        verbose_name_plural = _("Landing destination events")
