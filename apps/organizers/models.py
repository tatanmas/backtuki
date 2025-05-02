"""Models for the organizers app."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_tenants.models import TenantMixin, DomainMixin
from core.models import TimeStampedModel, UUIDModel
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context


class Organizer(TenantMixin, TimeStampedModel):
    """Organizer model representing a tenant in the platform."""
    
    ORGANIZATION_SIZE_CHOICES = (
        ('small', _('Small (1-10 employees)')),
        ('medium', _('Medium (11-50 employees)')),
        ('large', _('Large (51+ employees)')),
    )

    STATUS_CHOICES = (
        ('pending', _('Pending')),
        ('onboarding', _('Onboarding')),
        ('active', _('Active')),
        ('suspended', _('Suspended')),
    )
    
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
    
    # Organization details
    organization_size = models.CharField(
        _("organization size"),
        max_length=20,
        choices=ORGANIZATION_SIZE_CHOICES,
        blank=True
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    onboarding_completed = models.BooleanField(_("onboarding completed"), default=False)
    
    # Module activation
    has_events_module = models.BooleanField(_("has events module"), default=True)
    has_accommodation_module = models.BooleanField(_("has accommodation module"), default=False)
    has_experience_module = models.BooleanField(_("has experience module"), default=False)
    
    # Representative contact information
    representative_name = models.CharField(_("representative name"), max_length=255, blank=True)
    representative_email = models.EmailField(_("representative email"), blank=True)
    representative_phone = models.CharField(_("representative phone"), max_length=30, blank=True)
    
    auto_create_schema = True
    
    class Meta:
        verbose_name = _("organizer")
        verbose_name_plural = _("organizers")
    
    def __str__(self):
        return self.name


class OrganizerOnboarding(TimeStampedModel):
    """Stores the onboarding survey responses for an organizer."""
    
    EXPERIENCE_CHOICES = (
        ('yes', _('Yes')),
        ('no', _('No')),
    )
    
    EXPERIENCE_YEARS_CHOICES = (
        ('0-1', _('Less than 1 year')),
        ('1-3', _('1-3 years')),
        ('3+', _('More than 3 years')),
    )
    
    EVENT_SIZE_CHOICES = (
        ('small', _('Small (less than 100 people)')),
        ('medium', _('Medium (100-500 people)')),
        ('large', _('Large (more than 500 people)')),
    )
    
    EXPERIENCE_TYPE_CHOICES = (
        ('tours', _('Tours and guided visits')),
        ('workshops', _('Workshops and classes')),
        ('activities', _('Recreational activities')),
    )
    
    EXPERIENCE_FREQUENCY_CHOICES = (
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly or less')),
    )
    
    ACCOMMODATION_TYPE_CHOICES = (
        ('hotel', _('Hotel or inn')),
        ('apartment', _('Apartments or houses')),
        ('cabins', _('Cabins or glamping')),
    )
    
    ACCOMMODATION_CAPACITY_CHOICES = (
        ('small', _('Small (1-10 rooms/units)')),
        ('medium', _('Medium (11-50 rooms/units)')),
        ('large', _('Large (more than 50 rooms/units)')),
    )

    id = models.UUIDField(
        primary_key=True,
        default=UUIDModel._meta.get_field('id').default,
        editable=False
    )
    organizer = models.OneToOneField(
        Organizer,
        on_delete=models.CASCADE,
        related_name='onboarding'
    )
    
    # Module Selection (Step 1)
    selected_types = models.JSONField(_("selected modules"), default=list)
    
    # Organization Information (Step 2)
    organization_name = models.CharField(_("organization name"), max_length=255, blank=True)
    organization_slug = models.CharField(_("organization slug"), max_length=255, blank=True)
    organization_size = models.CharField(
        _("organization size"),
        max_length=20,
        choices=Organizer.ORGANIZATION_SIZE_CHOICES,
        blank=True
    )
    
    # Representative Information (Step 3)
    contact_name = models.CharField(_("contact name"), max_length=255, blank=True)
    contact_email = models.EmailField(_("contact email"), blank=True)
    contact_phone = models.CharField(_("contact phone"), max_length=30, blank=True)
    
    # Module-specific information
    # Events configuration
    has_experience = models.CharField(
        _("has previous experience"),
        max_length=5,
        choices=EXPERIENCE_CHOICES,
        blank=True
    )
    experience_years = models.CharField(
        _("experience years"),
        max_length=5,
        choices=EXPERIENCE_YEARS_CHOICES,
        blank=True
    )
    event_size = models.CharField(
        _("event size"),
        max_length=10,
        choices=EVENT_SIZE_CHOICES,
        blank=True
    )
    
    # Experiences configuration
    experience_type = models.CharField(
        _("experience type"),
        max_length=20,
        choices=EXPERIENCE_TYPE_CHOICES,
        blank=True
    )
    experience_frequency = models.CharField(
        _("experience frequency"),
        max_length=10,
        choices=EXPERIENCE_FREQUENCY_CHOICES,
        blank=True
    )
    
    # Accommodations configuration
    accommodation_type = models.CharField(
        _("accommodation type"),
        max_length=20,
        choices=ACCOMMODATION_TYPE_CHOICES,
        blank=True
    )
    accommodation_capacity = models.CharField(
        _("accommodation capacity"),
        max_length=10,
        choices=ACCOMMODATION_CAPACITY_CHOICES,
        blank=True
    )
    
    # Onboarding step tracking
    completed_step = models.IntegerField(_("completed step"), default=0)
    is_completed = models.BooleanField(_("is completed"), default=False)
    
    class Meta:
        verbose_name = _("organizer onboarding")
        verbose_name_plural = _("organizer onboardings")
    
    def __str__(self):
        return f"Onboarding for {self.organizer.name}"
    
    def save(self, *args, **kwargs):
        """Update organizer modules based on selections."""
        is_new = self._state.adding  # Check if it's a new record
        
        # First save the model itself
        super().save(*args, **kwargs)
        
        # Update organizer based on onboarding data
        if self.is_completed and self.organizer:
            User = get_user_model()
            
            # Ensure we're in the public schema for tenant operations
            with schema_context('public'):
                # Check if we're creating a new tenant or updating an existing one
                creating_tenant = self.organizer.status == 'pending' or self.organizer.status == 'onboarding'
                
                # Update modules based on selection
                if isinstance(self.selected_types, list):
                    self.organizer.has_events_module = 'events' in self.selected_types
                    self.organizer.has_experience_module = 'experiences' in self.selected_types
                    self.organizer.has_accommodation_module = 'accommodations' in self.selected_types
                
                # Update organization details
                if self.organization_name:
                    self.organizer.name = self.organization_name
                if self.organization_slug:
                    self.organizer.slug = self.organization_slug
                if self.organization_size:
                    self.organizer.organization_size = self.organization_size
                    
                # Update representative details
                if self.contact_name:
                    self.organizer.representative_name = self.contact_name
                if self.contact_email:
                    self.organizer.representative_email = self.contact_email
                    self.organizer.contact_email = self.contact_email
                    
                    # Link user to organizer if this is a new tenant and the user exists
                    if creating_tenant:
                        try:
                            user = User.objects.get(email=self.contact_email)
                            # Create the user-organizer link if it doesn't exist
                            self.organizer.organizer_users.get_or_create(
                                user=user,
                                defaults={
                                    'is_admin': True,
                                    'can_manage_events': True,
                                    'can_manage_accommodations': True,
                                    'can_manage_experiences': True,
                                    'can_view_reports': True,
                                    'can_manage_settings': True
                                }
                            )
                        except User.DoesNotExist:
                            # User doesn't exist yet - that's ok, they'll need to register
                            pass
                        
                if self.contact_phone:
                    self.organizer.representative_phone = self.contact_phone
                    self.organizer.contact_phone = self.contact_phone
                
                # Set onboarding as completed and activate tenant
                self.organizer.onboarding_completed = True
                self.organizer.status = 'active'
                self.organizer.save()


class BillingDetails(TimeStampedModel):
    """
    Billing information for an organizer.
    """
    PERSON_TYPE_CHOICES = (
        ('natural', _('Natural Person')),
        ('juridica', _('Legal Entity')),
    )
    
    DOCUMENT_TYPE_CHOICES = (
        ('invoice', _('Invoice')),
        ('receipt', _('Receipt')),
    )
    
    id = models.UUIDField(
        primary_key=True,
        default=UUIDModel._meta.get_field('id').default,
        editable=False
    )
    organizer = models.OneToOneField(
        Organizer,
        on_delete=models.CASCADE,
        related_name='billing_details'
    )
    person_type = models.CharField(
        _("person type"),
        max_length=10,
        choices=PERSON_TYPE_CHOICES,
        default='natural'
    )
    tax_name = models.CharField(_("tax name"), max_length=255)
    tax_id = models.CharField(_("tax ID"), max_length=20)
    billing_address = models.CharField(_("billing address"), max_length=255)
    document_type = models.CharField(
        _("document type"),
        max_length=10,
        choices=DOCUMENT_TYPE_CHOICES,
        default='invoice'
    )
    
    class Meta:
        verbose_name = _("billing details")
        verbose_name_plural = _("billing details")
    
    def __str__(self):
        return f"Billing for {self.organizer.name}"


class BankingDetails(TimeStampedModel):
    """
    Banking information for an organizer to receive payments.
    """
    id = models.UUIDField(
        primary_key=True,
        default=UUIDModel._meta.get_field('id').default,
        editable=False
    )
    organizer = models.OneToOneField(
        Organizer,
        on_delete=models.CASCADE,
        related_name='banking_details'
    )
    bank_name = models.CharField(_("bank name"), max_length=100)
    account_type = models.CharField(_("account type"), max_length=50)
    account_number = models.CharField(_("account number"), max_length=50)
    account_holder = models.CharField(_("account holder"), max_length=255)
    
    class Meta:
        verbose_name = _("banking details")
        verbose_name_plural = _("banking details")
    
    def __str__(self):
        return f"Banking for {self.organizer.name}"


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