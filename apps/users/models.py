"""Models for the users app."""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from core.models import TimeStampedModel


class User(AbstractUser, TimeStampedModel):
    """Custom user model for Tuki platform."""
    
    email = models.EmailField(
        _('email address'),
        unique=True,
        error_messages={
            'unique': _("A user with that email already exists."),
        }
    )
    phone_number = models.CharField(
        _("phone number"), 
        max_length=30, 
        blank=True, 
        null=True
    )
    profile_picture = models.ImageField(
        _("profile picture"),
        upload_to='users/profile_pictures',
        blank=True,
        null=True
    )
    
    # Custom fields for user types
    is_organizer = models.BooleanField(
        _("organizer status"),
        default=False,
        help_text=_("Designates whether this user is an organizer."),
    )
    is_validator = models.BooleanField(
        _("validator status"),
        default=False,
        help_text=_("Designates whether this user can validate tickets."),
    )
    
    # For django-tenants compatibility, used to filter users by tenant
    tenant_id = models.CharField(
        _("tenant ID"),
        max_length=50,
        blank=True,
        null=True,
        db_index=True
    )

    # Track password changes
    last_password_change = models.DateTimeField(
        _("last password change"),
        default=timezone.now,
        help_text=_("When the password was last changed.")
    )
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ['-date_joined']
    
    def __str__(self):
        return self.email
    
    def get_full_name(self):
        """Return the user's full name."""
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip() or self.username
    
    @property
    def is_client(self):
        """Return True if the user is a regular client."""
        return not (self.is_organizer or self.is_validator or self.is_staff)
    
    def save(self, *args, **kwargs):
        """Override save to handle tenant_id."""
        # Users can exist in the public schema or be associated with a tenant
        if not self.pk and not self.tenant_id:
            # Try to get current schema name from connection
            try:
                from django.db import connection
                if connection.schema_name != 'public':
                    self.tenant_id = connection.schema_name
            except:
                pass
        
        super().save(*args, **kwargs)


class Profile(TimeStampedModel):
    """Extended profile for users."""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    address = models.CharField(
        _("address"),
        max_length=255,
        blank=True,
        null=True
    )
    city = models.CharField(
        _("city"),
        max_length=100,
        blank=True,
        null=True
    )
    country = models.CharField(
        _("country"),
        max_length=100,
        blank=True,
        null=True
    )
    bio = models.TextField(
        _("bio"),
        blank=True,
        null=True
    )
    birth_date = models.DateField(
        _("birth date"),
        blank=True,
        null=True
    )
    
    class Meta:
        verbose_name = _("profile")
        verbose_name_plural = _("profiles")
    
    def __str__(self):
        return f"{self.user.email}'s profile" 