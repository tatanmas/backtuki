"""
Travel guides (blog Tuki): guías de viaje asociadas a destinos.

This is the same system that will be used for creator/influencer-owned guides later:
one model, one block schema, shared frontend components. When adding creator guides,
extend with an optional creator FK (or author_type) without changing the body structure.
"""

import secrets
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from .booking import ensure_embed_block_keys


class TravelGuide(BaseModel):
    """
    A travel guide (blog-style) linked to an optional destination.
    Supports multiple templates (editorial, multi_day_itinerary, best_activities).
    Designed for reuse: Tuki editorial guides now; creator/influencer guides later
    (same blocks, same components; optional creator FK can be added when needed).
    """

    TEMPLATE_CHOICES = [
        ('editorial', _('Editorial')),
        ('multi_day_itinerary', _('Multi-day itinerary')),
        ('best_activities', _('Best activities')),
    ]
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('published', _('Published')),
    ]

    destination = models.ForeignKey(
        'landing_destinations.LandingDestination',
        on_delete=models.SET_NULL,
        related_name='guide_entries',
        verbose_name=_('destination'),
        null=True,
        blank=True,
    )
    template = models.CharField(
        _('template'),
        max_length=40,
        choices=TEMPLATE_CHOICES,
        default='editorial',
    )
    title = models.CharField(_('title'), max_length=255)
    slug = models.SlugField(_('slug'), max_length=255, unique=True, db_index=True)
    excerpt = models.TextField(_('excerpt'), blank=True)
    hero_media_id = models.UUIDField(
        _('hero image from media library'),
        null=True,
        blank=True,
    )
    hero_image = models.URLField(_('hero image URL fallback'), max_length=500, blank=True)
    hero_slides = models.JSONField(
        _('hero slider slides'),
        default=list,
        blank=True,
        help_text=_(
            'List of { "media_id": "uuid", "caption": "" } for hero slider. '
            'If non-empty, hero is shown as slider like Erasmus; else hero_media_id/hero_image used as single image.'
        ),
    )
    body = models.JSONField(
        _('body'),
        default=list,
        blank=True,
        help_text=_(
            'List of blocks: paragraph, heading, image, itinerary, '
            'embed_experience, embed_experiences, embed_accommodation, embed_destination, embed_event, '
            'embed_erasmus_activity, embed_erasmus_activities, blockquote, gallery, checklist, '
            'countdown, cta_button'
        ),
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        db_index=True,
    )
    published_at = models.DateTimeField(_('published at'), null=True, blank=True)
    display_order = models.PositiveIntegerField(_('display order'), default=0)
    meta_title = models.CharField(_('meta title'), max_length=255, blank=True)
    meta_description = models.TextField(_('meta description'), blank=True)
    og_image = models.URLField(_('og image URL'), max_length=500, blank=True)
    preview_token = models.CharField(
        _('preview token'),
        max_length=64,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
        help_text=_('Secret token for viewing draft; used in URL ?preview_token=...'),
    )

    class Meta:
        verbose_name = _('Travel Guide')
        verbose_name_plural = _('Travel Guides')
        ordering = ['display_order', '-published_at', '-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.status == 'draft' and not self.preview_token:
            self.preview_token = secrets.token_urlsafe(32)
        self.body = ensure_embed_block_keys(self.body or [])
        super().save(*args, **kwargs)
