"""Base models for the Tuki platform."""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class TenantAwareModel(models.Model):
    """Base abstract model for tenant-aware models."""
    
    tenant_id = models.CharField(max_length=50, db_index=True)
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        """Override save to automatically set tenant_id."""
        if not self.tenant_id:
            # Get the current tenant from connection
            from django.db import connection
            self.tenant_id = connection.schema_name
            
        super().save(*args, **kwargs)


class TimeStampedModel(models.Model):
    """Base abstract model with created and updated timestamps."""
    
    created_at = models.DateTimeField(
        _("Created at"), auto_now_add=True, db_index=True
    )
    updated_at = models.DateTimeField(
        _("Updated at"), auto_now=True
    )
    
    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Base abstract model with UUID as primary key."""
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    class Meta:
        abstract = True


class BaseModel(TenantAwareModel, TimeStampedModel, UUIDModel):
    """Base model for all Tuki models."""
    
    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Base abstract model with soft delete functionality."""
    
    is_active = models.BooleanField(_("Active"), default=True)
    deleted_at = models.DateTimeField(_("Deleted at"), null=True, blank=True)
    
    class Meta:
        abstract = True 