"""
🚀 ENTERPRISE MEDIA LIBRARY MODELS
Centralized asset management with soft-delete, usage tracking, and multi-scope support.
"""

import os
import hashlib
import uuid
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from PIL import Image
from io import BytesIO

from core.models import BaseModel
from apps.organizers.models import Organizer
from django.contrib.auth import get_user_model

User = get_user_model()


def get_media_upload_path(instance, filename):
    """
    Generate upload path for media assets.
    
    Organizer-scoped: {organizer.slug}/YYYY/MM/DD/{uuid}.{ext}
    Global-scoped: global/YYYY/MM/DD/{uuid}.{ext}
    
    Note: MEDIA_URL already includes '/media/', so we don't duplicate it here.
    Note: If organizer is not yet assigned (during initial save), use 'temp' prefix.
    The organizer will be assigned in perform_create before the final save.
    """
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    date_path = timezone.now().strftime('%Y/%m/%d')
    
    # If organizer is not yet assigned, use temp path (will be corrected in perform_create)
    if instance.scope == 'organizer' and instance.organizer and hasattr(instance.organizer, 'slug'):
        # Don't include 'media' here - MEDIA_URL already has it
        return os.path.join(instance.organizer.slug, date_path, unique_filename)
    elif instance.scope == 'organizer':
        # Temporary path for organizer-scoped assets before organizer is assigned
        return os.path.join('temp', date_path, unique_filename)
    else:
        # Global assets: global/YYYY/MM/DD/{uuid}.{ext}
        return os.path.join('global', date_path, unique_filename)


class MediaAsset(BaseModel):
    """
    Media asset model for storing images/files.
    
    🚀 ENTERPRISE FEATURES:
    - Multi-scope (organizer/global)
    - Soft delete with usage tracking
    - Automatic image metadata extraction
    - SHA256 deduplication support
    - Usage tracking via MediaUsage
    """
    
    SCOPE_CHOICES = (
        ('organizer', _('Organizer')),
        ('global', _('Global')),
    )
    
    ALLOWED_CONTENT_TYPES = [
        'image/jpeg',
        'image/png',
        'image/webp',
        'image/gif'
    ]
    
    MAX_FILE_SIZE_MB = 10
    
    scope = models.CharField(
        _("scope"),
        max_length=20,
        choices=SCOPE_CHOICES,
        default='organizer',
        help_text=_("Asset scope: organizer-specific or global (site-wide)")
    )
    
    organizer = models.ForeignKey(
        Organizer,
        on_delete=models.CASCADE,
        related_name='media_assets',
        verbose_name=_("organizer"),
        null=True,
        blank=True,
        help_text=_("Owner organizer (required if scope=organizer)")
    )
    
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='uploaded_media',
        verbose_name=_("uploaded by"),
        null=True,
        blank=True
    )
    
    file = models.ImageField(
        _("file"),
        upload_to=get_media_upload_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'gif']
            )
        ]
    )
    
    original_filename = models.CharField(
        _("original filename"),
        max_length=255
    )
    
    content_type = models.CharField(
        _("content type"),
        max_length=100
    )
    
    size_bytes = models.BigIntegerField(
        _("size in bytes"),
        default=0
    )
    
    width = models.PositiveIntegerField(
        _("width"),
        null=True,
        blank=True
    )
    
    height = models.PositiveIntegerField(
        _("height"),
        null=True,
        blank=True
    )
    
    sha256 = models.CharField(
        _("SHA256 hash"),
        max_length=64,
        blank=True,
        help_text=_("For deduplication")
    )
    
    # Soft delete
    deleted_at = models.DateTimeField(
        _("deleted at"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("media asset")
        verbose_name_plural = _("media assets")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['scope', 'organizer', '-created_at']),
            models.Index(fields=['sha256']),
            models.Index(fields=['deleted_at']),
        ]
    
    def __str__(self):
        return f"{self.original_filename} ({self.scope})"
    
    def save(self, *args, **kwargs):
        """Extract image metadata on save."""
        if self.file and not self.width:
            try:
                img = Image.open(self.file)
                self.width, self.height = img.size
                self.content_type = f"image/{img.format.lower()}" if img.format else self.content_type
            except Exception as e:
                # Log but don't fail
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to extract image metadata: {e}")
        
        super().save(*args, **kwargs)
    
    def soft_delete(self):
        """Soft delete the asset."""
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])
    
    def restore(self):
        """Restore soft-deleted asset."""
        self.deleted_at = None
        self.save(update_fields=['deleted_at'])
    
    @property
    def url(self):
        """
        Return public URL for the asset.
        
        🚀 ENTERPRISE: Generates correct URLs for both local development and GCS production.
        - Local: Constructs absolute URL with http://localhost:8000
        - GCS: Uses PublicGoogleCloudStorage.url() -> https://storage.googleapis.com/{bucket}/{file.name}
        """
        if not self.file:
            return None
        
        from django.conf import settings
        
        # For GCS (production), use storage backend URL method directly
        # Check if using GCS storage backend
        storage_class = getattr(settings, 'DEFAULT_FILE_STORAGE', '')
        if 'PublicGoogleCloudStorage' in storage_class or 'GoogleCloudStorage' in storage_class:
            return self.file.url
        
        # For FileSystemStorage (local/homeserver): build absolute URL from BACKEND_URL
        relative_url = self.file.url

        if relative_url.startswith(('http://', 'https://')):
            return relative_url

        relative_url = relative_url.lstrip('/')
        base_url = getattr(settings, 'BACKEND_URL', None)
        if not base_url and getattr(settings, 'DEBUG', False):
            base_url = 'http://localhost:8000'
        if not base_url:
            allowed = getattr(settings, 'ALLOWED_HOSTS', [])
            if isinstance(allowed, str):
                allowed = [h.strip() for h in allowed.split(',') if h.strip()]
            for host in (allowed if isinstance(allowed, (list, tuple)) else [allowed]):
                if host and host not in ('*', 'localhost', '127.0.0.1'):
                    base_url = f"https://{host}"
                    break
        if not base_url:
            base_url = 'http://localhost:8000'
        return f"{base_url.rstrip('/')}/{relative_url}"
    
    @property
    def size_mb(self):
        """Return size in MB."""
        return round(self.size_bytes / (1024 * 1024), 2)
    
    @property
    def is_deleted(self):
        """Check if asset is soft-deleted."""
        return self.deleted_at is not None
    
    def usage_count(self):
        """Return number of places where this asset is used."""
        return self.usages.filter(deleted_at__isnull=True).count()


class MediaUsage(BaseModel):
    """
    Track where MediaAssets are used.
    
    🚀 ENTERPRISE: Generic foreign key to Event, Experience, Accommodation, etc.
    """
    
    asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.CASCADE,
        related_name='usages',
        verbose_name=_("asset")
    )
    
    # Generic relation to any model (Event, Experience, etc.)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE
    )
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    field_name = models.CharField(
        _("field name"),
        max_length=100,
        help_text=_("Which field uses this asset (e.g., 'main_image', 'gallery')")
    )
    
    # Soft delete
    deleted_at = models.DateTimeField(
        _("deleted at"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("media usage")
        verbose_name_plural = _("media usages")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['asset', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.asset.original_filename} used by {self.content_object}"
    
    def soft_delete(self):
        """Soft delete the usage."""
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])

