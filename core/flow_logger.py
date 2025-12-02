"""
🚀 ENTERPRISE: Flow Logger - Centralized flow tracking utility

This module provides a simple, robust API for tracking end-to-end business flows
across the platform without requiring external logging services.

Usage Examples:

    # 1. Start a flow at order creation
    from core.flow_logger import FlowLogger
    
    flow = FlowLogger.start_flow(
        'ticket_checkout',
        user=user,
        event=event,
        organizer=event.organizer,
        metadata={'ip_address': request.META.get('REMOTE_ADDR')}
    )
    
    # 2. Log events as the flow progresses
    flow.log_event(
        'ORDER_CREATED',
        order=order,
        message=f"Order {order.order_number} created",
        metadata={'total': float(order.total), 'currency': order.currency}
    )
    
    # 3. Attach flow_id to order for tracking
    order.flow = flow.flow
    order.save()
    
    # 4. Complete the flow
    flow.complete(message="All tickets sent successfully")
    
    # 5. Or mark as failed
    flow.fail(message="Email delivery failed", error=exception)

Design Principles:
- Non-blocking: All operations are fast database writes
- Fail-safe: Errors in logging don't break business logic
- Queryable: All data stored in structured DB tables
- Extensible: Metadata fields support arbitrary JSON data
"""

from django.utils import timezone
from django.db import transaction
from core.models import PlatformFlow, PlatformFlowEvent
import logging

logger = logging.getLogger(__name__)


class FlowLogger:
    """
    Utility class for tracking platform flows.
    
    Provides a clean API for creating flows and logging events within them.
    All operations are wrapped in try/except to ensure logging failures
    don't break business logic.
    """
    
    def __init__(self, flow: PlatformFlow):
        """
        Initialize with an existing flow.
        
        Args:
            flow: PlatformFlow instance to log events to
        """
        self.flow = flow
    
    @classmethod
    def start_flow(cls, flow_type: str, user=None, organizer=None, event=None, 
                   experience=None, metadata=None):
        """
        Start a new platform flow.
        
        Args:
            flow_type: Type of flow ('ticket_checkout', 'experience_booking', etc.)
            user: User initiating the flow (optional)
            organizer: Organizer associated with the flow (optional)
            event: Event being purchased/booked (optional)
            experience: Experience being booked (optional)
            metadata: Additional flow-level data as dict (optional)
        
        Returns:
            FlowLogger instance for logging events
        
        Example:
            flow = FlowLogger.start_flow(
                'ticket_checkout',
                user=request.user,
                event=event,
                organizer=event.organizer,
                metadata={'session_id': request.session.session_key}
            )
        """
        try:
            flow = PlatformFlow.objects.create(
                flow_type=flow_type,
                status='in_progress',
                user=user,
                organizer=organizer,
                event=event,
                experience=experience,
                metadata=metadata or {}
            )
            logger.info(
                f"🚀 [FLOW] Started {flow_type} flow: {flow.id} "
                f"(user: {user.id if user else 'N/A'}, "
                f"organizer: {organizer.id if organizer else 'N/A'})"
            )
            return cls(flow)
        except Exception as e:
            logger.error(f"❌ [FLOW] Failed to start flow: {e}", exc_info=True)
            # Return a dummy logger that doesn't break the flow
            return cls(None)
    
    @classmethod
    def from_flow_id(cls, flow_id):
        """
        Create FlowLogger from existing flow ID.
        
        Useful when continuing a flow from a different context (e.g., Celery task).
        
        Args:
            flow_id: UUID of existing PlatformFlow
        
        Returns:
            FlowLogger instance or None if flow not found
        
        Example:
            # In Celery task
            flow = FlowLogger.from_flow_id(order.flow_id)
            if flow:
                flow.log_event('EMAIL_TASK_STARTED', order=order)
        """
        try:
            flow = PlatformFlow.objects.get(id=flow_id)
            return cls(flow)
        except PlatformFlow.DoesNotExist:
            logger.warning(f"⚠️ [FLOW] Flow {flow_id} not found")
            return None
        except Exception as e:
            logger.error(f"❌ [FLOW] Error loading flow {flow_id}: {e}", exc_info=True)
            return None
    
    def log_event(self, step: str, source='api', status='info', message='', 
                  order=None, payment=None, email_log=None, celery_task_log=None, 
                  metadata=None):
        """
        Log an event in the flow.
        
        Args:
            step: Step name (must be in PlatformFlowEvent.STEP_CHOICES)
            source: Event source ('api', 'celery', 'payment_gateway', 'system')
            status: Event status ('success', 'failure', 'info', 'warning')
            message: Human-readable message describing the event
            order: Order instance (optional)
            payment: Payment instance (optional)
            email_log: EmailLog instance (optional)
            celery_task_log: CeleryTaskLog instance (optional)
            metadata: Step-specific data as dict (optional)
        
        Returns:
            PlatformFlowEvent instance or None if logging failed
        
        Example:
            flow.log_event(
                'PAYMENT_AUTHORIZED',
                source='payment_gateway',
                status='success',
                message=f"Payment {payment.buy_order} authorized",
                payment=payment,
                metadata={'amount': float(payment.amount), 'method': payment.payment_method.display_name}
            )
        """
        if not self.flow:
            # Dummy logger, skip silently
            return None
        
        try:
            event = PlatformFlowEvent.objects.create(
                flow=self.flow,
                step=step,
                source=source,
                status=status,
                message=message,
                order=order,
                payment=payment,
                email_log=email_log,
                celery_task_log=celery_task_log,
                metadata=metadata or {}
            )
            
            # Log to standard logger as well for immediate visibility
            emoji = {
                'success': '✅',
                'failure': '❌',
                'info': '📊',
                'warning': '⚠️'
            }.get(status, '📊')
            
            logger.info(
                f"{emoji} [FLOW {str(self.flow.id)[:8]}] {step} - {status}: {message}"
            )
            
            return event
        except Exception as e:
            logger.error(
                f"❌ [FLOW {str(self.flow.id)[:8]}] Failed to log event {step}: {e}",
                exc_info=True
            )
            return None
    
    def update_order(self, order):
        """
        Update the primary order reference in the flow.
        
        Args:
            order: Order instance to set as primary_order
        
        Example:
            flow.update_order(order)
        """
        if not self.flow:
            return
        
        try:
            self.flow.primary_order = order
            self.flow.save(update_fields=['primary_order'])
            logger.info(f"📊 [FLOW {str(self.flow.id)[:8]}] Updated primary order: {order.order_number}")
        except Exception as e:
            logger.error(
                f"❌ [FLOW {str(self.flow.id)[:8]}] Failed to update order: {e}",
                exc_info=True
            )
    
    def complete(self, message='Flow completed successfully', metadata=None):
        """
        Mark flow as completed with duration tracking.
        
        Args:
            message: Completion message
            metadata: Additional completion metadata (optional)
        
        Example:
            flow.complete(
                message="Order paid and tickets sent",
                metadata={'total_duration_ms': 8500}
            )
        """
        if not self.flow:
            return
        
        try:
            self.flow.status = 'completed'
            self.flow.completed_at = timezone.now()
            
            # 🚀 ENTERPRISE: Calculate duration in milliseconds
            if self.flow.created_at and self.flow.completed_at:
                duration = self.flow.completed_at - self.flow.created_at
                self.flow.duration_ms = int(duration.total_seconds() * 1000)
            
            # Merge metadata with duration
            if metadata:
                self.flow.metadata.update(metadata)
            
            self.flow.save(update_fields=['status', 'completed_at', 'duration_ms', 'metadata'])
            
            self.log_event('FLOW_COMPLETED', status='success', message=message, metadata=metadata)
            logger.info(f"✅ [FLOW {str(self.flow.id)[:8]}] Completed in {self.flow.duration_ms}ms: {message}")
        except Exception as e:
            logger.error(
                f"❌ [FLOW {str(self.flow.id)[:8]}] Failed to mark as completed: {e}",
                exc_info=True
            )
    
    def fail(self, message='Flow failed', error=None):
        """
        Mark flow as failed.
        
        Args:
            message: Failure message
            error: Exception object (optional)
        
        Example:
            try:
                # ... business logic ...
            except Exception as e:
                flow.fail(message="Payment processing failed", error=e)
                raise
        """
        if not self.flow:
            return
        
        try:
            self.flow.status = 'failed'
            self.flow.failed_at = timezone.now()
            self.flow.save(update_fields=['status', 'failed_at'])
            
            metadata = {}
            if error:
                metadata['error'] = str(error)
                metadata['error_type'] = type(error).__name__
            
            self.log_event('FLOW_FAILED', status='failure', message=message, metadata=metadata)
            logger.error(f"❌ [FLOW {str(self.flow.id)[:8]}] Failed: {message}")
        except Exception as e:
            logger.error(
                f"❌ [FLOW {str(self.flow.id)[:8]}] Failed to mark as failed: {e}",
                exc_info=True
            )
    
    def abandon(self, message='Flow abandoned by user'):
        """
        Mark flow as abandoned (e.g., user closed checkout without paying).
        
        Args:
            message: Abandonment message
        
        Example:
            # Called when reservation expires without payment
            flow.abandon(message="Reservation expired without payment")
        """
        if not self.flow:
            return
        
        try:
            self.flow.status = 'abandoned'
            self.flow.save(update_fields=['status'])
            
            self.log_event('FLOW_ABANDONED', status='info', message=message)
            logger.info(f"⚠️ [FLOW {str(self.flow.id)[:8]}] Abandoned: {message}")
        except Exception as e:
            logger.error(
                f"❌ [FLOW {str(self.flow.id)[:8]}] Failed to mark as abandoned: {e}",
                exc_info=True
            )
    
    @property
    def flow_id(self):
        """Get the flow ID (UUID) as string."""
        return str(self.flow.id) if self.flow else None
    
    def __bool__(self):
        """Check if this is a valid (non-dummy) logger."""
        return self.flow is not None

