"""Base models for the Tuki platform."""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """Abstract base model that provides self-updating created_at and updated_at fields."""
    
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)
    
    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Abstract base model that provides a UUID primary key."""
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    class Meta:
        abstract = True


class BaseModel(TimeStampedModel, UUIDModel):
    """Base model for all Tuki models."""
    
    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Base abstract model with soft delete functionality."""
    
    is_active = models.BooleanField(_("Active"), default=True)
    deleted_at = models.DateTimeField(_("Deleted at"), null=True, blank=True)
    
    class Meta:
        abstract = True 