"""Models for the organizers app."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_tenants.models import TenantMixin, DomainMixin
from core.models import TimeStampedModel, UUIDModel


class Organizer(TenantMixin, TimeStampedModel):
    """Organizer model representing a tenant in the platform."""
    
    id = models.UUIDField(
        primary_key=True,
        default=UUIDModel._meta.get_field('id').default,
        editable=False
    )
    name = models.CharField(_("name"), max_length=255)
    slug = models.SlugField(_("slug"), unique=True)
    description = models.TextField(_("description"), blank=True)
    logo = models.ImageField(
        _("logo"),
        upload_to='organizers/logos',
        blank=True,
        null=True
    )
    website = models.URLField(_("website"), blank=True)
    contact_email = models.EmailField(_("contact email"))
    contact_phone = models.CharField(_("contact phone"), max_length=30, blank=True)
    address = models.CharField(_("address"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    country = models.CharField(_("country"), max_length=100, blank=True)
    
    # Module activation
    has_events_module = models.BooleanField(_("has events module"), default=True)
    has_accommodation_module = models.BooleanField(_("has accommodation module"), default=False)
    has_experience_module = models.BooleanField(_("has experience module"), default=False)
    
    auto_create_schema = True
    
    class Meta:
        verbose_name = _("organizer")
        verbose_name_plural = _("organizers")
    
    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """Domain model for tenant domains."""
    
    class Meta:
        verbose_name = _("domain")
        verbose_name_plural = _("domains")


class OrganizerUser(TimeStampedModel):
    """Link between users and organizers with specific roles."""
    
    id = models.UUIDField(
        primary_key=True,
        default=UUIDModel._meta.get_field('id').default,
        editable=False
    )
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='organizer_roles'
    )
    organizer = models.ForeignKey(
        Organizer,
        on_delete=models.CASCADE,
        related_name='organizer_users'
    )
    is_admin = models.BooleanField(_("is admin"), default=False)
    
    # Module permissions
    can_manage_events = models.BooleanField(_("can manage events"), default=False)
    can_manage_accommodations = models.BooleanField(_("can manage accommodations"), default=False)
    can_manage_experiences = models.BooleanField(_("can manage experiences"), default=False)
    can_view_reports = models.BooleanField(_("can view reports"), default=False)
    can_manage_settings = models.BooleanField(_("can manage settings"), default=False)
    
    class Meta:
        verbose_name = _("organizer user")
        verbose_name_plural = _("organizer users")
        unique_together = ('user', 'organizer')
    
    def __str__(self):
        return f"{self.user.email} @ {self.organizer.name}"


class OrganizerSubscription(TimeStampedModel):
    """Subscription plan for an organizer."""
    
    PLAN_CHOICES = (
        ('free', _('Free')),
        ('basic', _('Basic')),
        ('premium', _('Premium')),
        ('enterprise', _('Enterprise')),
    )
    
    STATUS_CHOICES = (
        ('active', _('Active')),
        ('trial', _('Trial')),
        ('canceled', _('Canceled')),
        ('expired', _('Expired')),
    )
    
    id = models.UUIDField(
        primary_key=True,
        default=UUIDModel._meta.get_field('id').default,
        editable=False
    )
    organizer = models.ForeignKey(
        Organizer,
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    plan = models.CharField(_("plan"), max_length=20, choices=PLAN_CHOICES)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"), null=True, blank=True)
    
    # Plan limits
    max_events = models.PositiveIntegerField(_("max events"), default=0)
    max_accommodations = models.PositiveIntegerField(_("max accommodations"), default=0)
    max_experiences = models.PositiveIntegerField(_("max experiences"), default=0)
    max_storage_gb = models.PositiveIntegerField(_("max storage (GB)"), default=0)
    max_users = models.PositiveIntegerField(_("max users"), default=1)
    
    class Meta:
        verbose_name = _("organizer subscription")
        verbose_name_plural = _("organizer subscriptions")
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.organizer.name} - {self.get_plan_display()}"
    
    @property
    def is_active(self):
        """Return True if the subscription is active."""
        return self.status in ['active', 'trial'] 