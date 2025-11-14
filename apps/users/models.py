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

    # --- Organizer helpers ---
    def get_primary_organizer_role(self):
        """
        Return the OrganizerUser instance that should be considered this
        user's primary organizer membership.
        """
        cached_role = getattr(self, '_cached_primary_organizer_role', None)
        if cached_role is not None:
            return cached_role

        if not hasattr(self, 'organizer_roles'):
            self._cached_primary_organizer_role = None
            return None

        organizer_user = (
            self.organizer_roles.select_related('organizer')
            .filter(is_admin=True)
            .order_by('created_at')
            .first()
        )

        if organizer_user is None:
            organizer_user = (
                self.organizer_roles.select_related('organizer')
                .order_by('created_at')
                .first()
            )

        self._cached_primary_organizer_role = organizer_user
        return organizer_user

    def get_primary_organizer(self):
        """
        Return the Organizer instance associated with this user via OrganizerUser.
        """
        organizer_role = self.get_primary_organizer_role()
        organizer = organizer_role.organizer if organizer_role else None
        setattr(self, '_cached_primary_organizer', organizer)
        return organizer
    
    def mark_profile_complete(self):
        """Mark the profile as completed."""
        self.is_guest = False
        self.profile_completed_at = timezone.now()
        self.save(update_fields=['is_guest', 'profile_completed_at'])
        
        # 🚀 ENTERPRISE: Vincular órdenes existentes cuando el usuario completa su perfil
        self.link_existing_orders()
    
    def link_existing_orders(self):
        """Vincular órdenes existentes que coincidan con el email del usuario."""
        from apps.events.models import Order
        
        # Buscar órdenes que tengan el mismo email pero no estén vinculadas a ningún usuario
        unlinked_orders = Order.objects.filter(
            email__iexact=self.email,
            user__isnull=True
        )
        
        count = unlinked_orders.count()
        if count > 0:
            print(f"🔗 [User.link_existing_orders] Linking {count} existing orders to user {self.email}")
            unlinked_orders.update(user=self)
            print(f"✅ [User.link_existing_orders] Successfully linked {count} orders")
        else:
            print(f"📝 [User.link_existing_orders] No unlinked orders found for {self.email}")
    
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