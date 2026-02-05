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


# 🚀 ENTERPRISE: Platform Flow Monitoring Models

class PlatformFlow(BaseModel):
    """
    🚀 ENTERPRISE: Tracks end-to-end flows across the platform.
    
    Supports tracking of complete user journeys from reservation to fulfillment
    for all product types: events, experiences, accommodations, and future products.
    
    This enables:
    - Complete audit trail of customer transactions
    - Debugging of failed flows in production
    - Analytics on conversion and fulfillment rates
    - SLA monitoring for critical operations
    """
    
    FLOW_TYPE_CHOICES = [
        ('ticket_checkout', 'Ticket Checkout (Events)'),
        ('experience_booking', 'Experience Booking'),
        ('accommodation_booking', 'Accommodation Booking'),
        ('tour_booking', 'Tour Booking'),
    ]
    
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('abandoned', 'Abandoned'),
    ]
    
    # Core fields
    flow_type = models.CharField(
        max_length=50, 
        choices=FLOW_TYPE_CHOICES, 
        db_index=True,
        help_text="Type of business flow being tracked"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='in_progress', 
        db_index=True,
        help_text="Current status of the flow"
    )
    
    # Business context
    user = models.ForeignKey(
        'users.User', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='flows',
        help_text="User who initiated the flow"
    )
    organizer = models.ForeignKey(
        'organizers.Organizer', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='flows',
        help_text="Organizer associated with the flow"
    )
    primary_order = models.ForeignKey(
        'events.Order', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='primary_flows',
        help_text="Primary order created in this flow"
    )
    
    # Optional product references (for filtering/analytics)
    event = models.ForeignKey(
        'events.Event', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='flows',
        help_text="Event associated with this flow (if applicable)"
    )
    experience = models.ForeignKey(
        'experiences.Experience', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='flows',
        help_text="Experience associated with this flow (if applicable)"
    )
    # TUKI Creators: attribution for creator commission
    creator = models.ForeignKey(
        'creators.CreatorProfile',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='flows',
        help_text="Creator (influencer) who referred this flow (for commission)"
    )
    # Future: accommodation field
    
    # Timing
    completed_at = models.DateTimeField(
        null=True, 
        blank=True, 
        db_index=True,
        help_text="When the flow completed successfully"
    )
    failed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the flow failed"
    )
    
    # Metadata for extensibility
    metadata = models.JSONField(
        default=dict, 
        blank=True, 
        help_text="Additional flow-specific data (totals, session info, etc.)"
    )
    
    # 🚀 ENTERPRISE: Latency metrics (added for performance monitoring)
    duration_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total duration of flow in milliseconds (for completed flows)"
    )
    
    class Meta:
        verbose_name = _("Platform Flow")
        verbose_name_plural = _("Platform Flows")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['flow_type', 'status', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['organizer', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['duration_ms']),  # For performance queries
        ]
    
    def __str__(self):
        return f"{self.get_flow_type_display()} - {self.status} ({str(self.id)[:8]})"


class PlatformFlowEvent(BaseModel):
    """
    🚀 ENTERPRISE: Individual events within a flow (granular audit trail).
    
    Each event represents a specific step in the flow, allowing reconstruction
    of the complete journey and identification of failure points.
    """
    
    STEP_CHOICES = [
        # Reservation steps
        ('RESERVATION_REQUESTED', 'Reservation Requested'),
        ('RESERVATION_CREATED', 'Reservation Created'),
        ('RESERVATION_EXPIRED', 'Reservation Expired'),
        
        # Order steps
        ('ORDER_CREATED', 'Order Created'),
        ('ORDER_MARKED_PAID', 'Order Marked as Paid'),
        ('ORDER_CANCELLED', 'Order Cancelled'),
        ('ORDER_REFUNDED', 'Order Refunded'),
        
        # Payment steps
        ('PAYMENT_REQUIRED', 'Payment Required'),
        ('PAYMENT_INITIATED', 'Payment Initiated'),
        ('PAYMENT_AUTHORIZED', 'Payment Authorized'),
        ('PAYMENT_FAILED', 'Payment Failed'),
        ('PAYMENT_CANCELLED', 'Payment Cancelled'),
        
        # Ticket/Booking steps
        ('HOLDER_DATA_STORED', 'Ticket Holder Data Stored'),
        ('TICKETS_CREATED', 'Tickets Created'),
        ('BOOKING_CONFIRMED', 'Booking Confirmed'),
        
        # Email steps
        ('EMAIL_PENDING', 'Email Pending - Will Send from Frontend'),
        ('EMAIL_SYNC_ATTEMPT', 'Email Sync Send Attempt'),
        ('EMAIL_TASK_ENQUEUED', 'Email Task Enqueued'),
        ('EMAIL_TASK_STARTED', 'Email Task Started'),
        ('EMAIL_SENT', 'Email Sent Successfully'),
        ('EMAIL_FAILED', 'Email Failed'),
        ('EMAIL_MANUAL_RESEND', 'Email Manual Resend'),
        
        # Coupon steps
        ('COUPON_APPLIED', 'Coupon Applied'),
        ('COUPON_VALIDATION_FAILED', 'Coupon Validation Failed'),
        
        # Flow completion
        ('FLOW_COMPLETED', 'Flow Completed Successfully'),
        ('FLOW_FAILED', 'Flow Failed'),
        ('FLOW_ABANDONED', 'Flow Abandoned'),
    ]
    
    SOURCE_CHOICES = [
        ('api', 'API'),
        ('celery', 'Celery Task'),
        ('payment_gateway', 'Payment Gateway'),
        ('system', 'System'),
    ]
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('info', 'Info'),
        ('warning', 'Warning'),
    ]
    
    # Core fields
    flow = models.ForeignKey(
        PlatformFlow, 
        on_delete=models.CASCADE, 
        related_name='events',
        help_text="Flow this event belongs to"
    )
    step = models.CharField(
        max_length=50, 
        choices=STEP_CHOICES, 
        db_index=True,
        help_text="Specific step in the flow"
    )
    source = models.CharField(
        max_length=20, 
        choices=SOURCE_CHOICES, 
        default='api',
        help_text="Source that generated this event"
    )
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='info',
        help_text="Status of this step"
    )
    
    # Context
    message = models.CharField(
        max_length=500, 
        blank=True,
        help_text="Human-readable message describing the event"
    )
    
    # Optional references to related entities
    order = models.ForeignKey(
        'events.Order', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='flow_events'
    )
    payment = models.ForeignKey(
        'payment_processor.Payment', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='flow_events'
    )
    email_log = models.ForeignKey(
        'events.EmailLog', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='flow_events'
    )
    celery_task_log = models.ForeignKey(
        'CeleryTaskLog', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='flow_events'
    )
    
    # Metadata for step-specific data
    metadata = models.JSONField(
        default=dict, 
        blank=True, 
        help_text="Step-specific data (totals, counts, errors, IDs, etc.)"
    )
    
    class Meta:
        verbose_name = _("Platform Flow Event")
        verbose_name_plural = _("Platform Flow Events")
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['flow', 'created_at']),
            models.Index(fields=['step', 'status', 'created_at']),
            models.Index(fields=['order', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.step} - {self.status} (Flow: {str(self.flow_id)[:8]})"


class CeleryTaskLog(BaseModel):
    """
    🚀 ENTERPRISE: Comprehensive logging of ALL Celery task executions.
    
    Automatically populated via Celery signals (task_prerun, task_postrun, etc.)
    to provide complete visibility into async task execution without depending
    on external logging services.
    
    Critical for debugging production issues with email delivery, payment processing,
    and other async operations.
    """
    
    STATUS_CHOICES = [
        ('started', 'Started'),
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('retry', 'Retry'),
    ]
    
    # Core task identification
    task_id = models.CharField(
        max_length=255, 
        db_index=True, 
        help_text="Celery task UUID (unique per execution)"
    )
    task_name = models.CharField(
        max_length=255, 
        db_index=True, 
        help_text="Full task path (e.g., apps.events.tasks.send_order_confirmation_email)"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        db_index=True,
        help_text="Current status of the task execution"
    )
    
    # Queue information
    queue = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Celery queue name (e.g., 'emails', 'critical')"
    )
    routing_key = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Routing key used for task"
    )
    
    # Payload (for debugging)
    args = models.JSONField(
        default=list, 
        blank=True,
        help_text="Positional arguments passed to task"
    )
    kwargs = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Keyword arguments passed to task"
    )
    result = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Task return value (if successful)"
    )
    
    # Error tracking
    error = models.TextField(
        blank=True,
        help_text="Error message if task failed"
    )
    traceback = models.TextField(
        blank=True,
        help_text="Full Python traceback if task failed"
    )
    
    # Business context (auto-detected from args/kwargs or explicitly passed)
    flow = models.ForeignKey(
        PlatformFlow, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='celery_logs',
        help_text="Flow this task belongs to (if applicable)"
    )
    order = models.ForeignKey(
        'events.Order', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='celery_logs',
        help_text="Order this task is processing (if applicable)"
    )
    user = models.ForeignKey(
        'users.User', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='celery_logs',
        help_text="User associated with this task (if applicable)"
    )
    
    # Timing (for performance analysis)
    duration_ms = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Task execution duration in milliseconds"
    )
    
    class Meta:
        verbose_name = _("Celery Task Log")
        verbose_name_plural = _("Celery Task Logs")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task_id']),
            models.Index(fields=['task_name', 'status', 'created_at']),
            models.Index(fields=['flow', 'created_at']),
            models.Index(fields=['order', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        task_short = self.task_name.split('.')[-1] if '.' in self.task_name else self.task_name
        return f"{task_short} [{self.status}] - {self.task_id[:8]}"


class Country(TimeStampedModel):
    """
    Country model for categorizing experiences and accommodations by country.
    Managed by SuperAdmin.
    """
    
    name = models.CharField(
        _("country name"),
        max_length=100,
        unique=True,
        help_text=_("Country name (e.g., 'Chile', 'Brasil', 'Colombia')")
    )
    code = models.CharField(
        _("country code"),
        max_length=3,
        unique=True,
        blank=True,
        null=True,
        help_text=_("ISO country code (optional, e.g., 'CHL', 'BRA')")
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Whether this country is active and can be assigned")
    )
    display_order = models.IntegerField(
        _("display order"),
        default=0,
        help_text=_("Order in which countries should be displayed (lower = first)")
    )
    
    class Meta:
        verbose_name = _("Country")
        verbose_name_plural = _("Countries")
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['is_active', 'display_order', 'name']),
        ]
    
    def __str__(self):
        return self.name 