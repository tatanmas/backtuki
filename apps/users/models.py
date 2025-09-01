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
    
    # Relationship with organizer
    organizer = models.ForeignKey(
        'organizers.Organizer',
        on_delete=models.SET_NULL,
        related_name='users',
        verbose_name=_("organizer"),
        null=True,
        blank=True
    )

    # Track password changes
    last_password_change = models.DateTimeField(
        _("last password change"),
        default=timezone.now,
        help_text=_("When the password was last changed.")
    )
    
    # Guest user tracking
    is_guest = models.BooleanField(
        _("guest status"),
        default=False,
        help_text=_("User created automatically from purchase, hasn't completed profile.")
    )
    
    # Profile completion tracking
    profile_completed_at = models.DateTimeField(
        _("profile completed at"),
        null=True,
        blank=True,
        help_text=_("When the user completed their profile.")
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
    
    @property
    def is_profile_complete(self):
        """Return True if the user has completed their profile."""
        return (
            self.first_name and 
            self.last_name and 
            not self.is_guest and
            self.profile_completed_at is not None
        )
    
    @property
    def has_password(self):
        """Return True if the user has set a password."""
        return bool(self.password)
    
    def mark_profile_complete(self):
        """Mark the profile as completed."""
        self.is_guest = False
        self.profile_completed_at = timezone.now()
        self.save(update_fields=['is_guest', 'profile_completed_at'])
    
    @classmethod
    def create_guest_user(cls, email, first_name=None, last_name=None):
        """Create a guest user from purchase."""
        # Generate a unique username from email
        username = email.split('@')[0]
        counter = 1
        original_username = username
        
        while cls.objects.filter(username=username).exists():
            username = f"{original_username}{counter}"
            counter += 1
        
        user = cls.objects.create_user(
            username=username,
            email=email,
            first_name=first_name or '',
            last_name=last_name or '',
            is_guest=True,
            password=None  # No password initially
        )
        
        return user


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