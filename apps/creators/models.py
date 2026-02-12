"""
TUKI Creators (influencers) models.
CreatorProfile: public profile and "Mis Recomendados" for creator shop.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from core.models import BaseModel


class CreatorProfile(BaseModel):
    """
    Creator (influencer) profile linked to a User.
    Public shop at /creators/<slug>/.
    """
    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='creator_profile',
        verbose_name=_("user"),
    )
    slug = models.SlugField(
        _("slug"),
        max_length=100,
        unique=True,
        help_text=_("URL handle for public profile (e.g. /creators/cata/)"),
    )
    display_name = models.CharField(_("display name"), max_length=255)
    bio = models.TextField(_("bio"), blank=True)
    avatar = models.URLField(
        _("avatar URL"),
        max_length=500,
        blank=True,
        help_text=_("Avatar image URL (or use media asset later)"),
    )
    location = models.CharField(_("location"), max_length=255, blank=True)
    phone = models.CharField(
        _("phone"),
        max_length=30,
        blank=True,
        help_text=_("For work group and notifications (e.g. WhatsApp)"),
    )
    social_links = models.JSONField(
        _("social links"),
        default=list,
        blank=True,
        help_text=_("List of {id, name, url, icon}"),
    )
    is_approved = models.BooleanField(
        _("is approved"),
        default=False,
        help_text=_("Whether creator can access dashboard and earn commissions"),
    )
    bank_details = models.JSONField(
        _("bank details"),
        default=dict,
        blank=True,
        help_text=_("Optional: { bank_name, account_type, account_number, rut?, holder_name } for payouts"),
    )

    class Meta:
        verbose_name = _("creator profile")
        verbose_name_plural = _("creator profiles")
        ordering = ['display_name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_approved']),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.slug})"


class CreatorRecommendedExperience(BaseModel):
    """M2M through model: experiences a creator recommends on their public profile."""
    creator = models.ForeignKey(
        CreatorProfile,
        on_delete=models.CASCADE,
        related_name='recommended_experiences',
        verbose_name=_("creator"),
    )
    experience = models.ForeignKey(
        'experiences.Experience',
        on_delete=models.CASCADE,
        related_name='recommended_by_creators',
        verbose_name=_("experience"),
    )
    order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("creator recommended experience")
        verbose_name_plural = _("creator recommended experiences")
        ordering = ['creator', 'order']
        unique_together = [['creator', 'experience']]
        indexes = [
            models.Index(fields=['creator', 'order']),
        ]

    def __str__(self):
        return f"{self.creator.slug} recommends {self.experience.title}"


class Relato(BaseModel):
    """
    Creator story (blog-style) with rich body (blocks: paragraph, heading, itinerary, image).
    Itinerary block uses same format as Experience: list of { time, title, description }.
    """
    creator = models.ForeignKey(
        CreatorProfile,
        on_delete=models.CASCADE,
        related_name='relatos',
        verbose_name=_("creator"),
    )
    title = models.CharField(_("title"), max_length=255)
    slug = models.SlugField(
        _("slug"),
        max_length=120,
        help_text=_("URL handle for this relato (unique per creator)"),
    )
    body = models.JSONField(
        _("body"),
        default=list,
        blank=True,
        help_text=_("List of blocks: paragraph, heading, itinerary, image. Itinerary items: { time, title, description }"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=[('draft', _('Draft')), ('published', _('Published'))],
        default='draft',
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    experience = models.ForeignKey(
        'experiences.Experience',
        on_delete=models.SET_NULL,
        related_name='relatos',
        verbose_name=_("linked experience"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("relato")
        verbose_name_plural = _("relatos")
        ordering = ['-created_at']
        unique_together = [['creator', 'slug']]
        indexes = [
            models.Index(fields=['creator', 'status']),
        ]

    def __str__(self):
        return f"{self.title} ({self.creator.slug})"


class PlatformLandingSlot(BaseModel):
    """
    Assign a MediaAsset to a named slot (e.g. creators landing hero, bento).
    SuperAdmin manages these from the media library.
    """
    slot_key = models.CharField(
        _("slot key"),
        max_length=100,
        unique=True,
        help_text=_("e.g. creators_landing_hero, creators_landing_bento_1"),
    )
    asset = models.ForeignKey(
        'media.MediaAsset',
        on_delete=models.SET_NULL,
        related_name='landing_slots',
        verbose_name=_("asset"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("platform landing slot")
        verbose_name_plural = _("platform landing slots")
        ordering = ['slot_key']

    def __str__(self):
        return f"{self.slot_key} -> {self.asset_id or 'unassigned'}"
