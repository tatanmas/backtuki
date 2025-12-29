"""
🚀 ENTERPRISE Celery Tasks for Experiences - Tuki Platform
Analogous to apps/events/tasks.py

Handles asynchronous operations for experiences:
- Email confirmation sending (with retry logic)
- Background processing

Usage:
    from apps.experiences.tasks import send_experience_confirmation_email
    
    send_experience_confirmation_email.apply_async(
        args=[str(order.id)],
        kwargs={'flow_id': str(flow.id)},
        queue='emails'
    )
"""

import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_experience_confirmation_email(self, order_id: str, to_email: str = None, flow_id: str = None):
    """
    🚀 ENTERPRISE: Send experience confirmation email (Celery fallback).
    Analogous to apps/events/tasks.py::send_order_confirmation_email
    
    Retry logic:
    - max_retries=3
    - default_retry_delay=60 seconds
    - Exponential backoff
    
    Args:
        order_id: UUID of the order
        to_email: Optional override email address
        flow_id: Optional flow ID for tracking
        
    Returns:
        Dict with status and metrics
    """
    try:
        from apps.experiences.email_sender import send_experience_confirmation_email_optimized
        from core.flow_logger import FlowLogger
        
        logger.info(f"📧 [CELERY_TASK_EXP] Starting email task for order {order_id} (attempt {self.request.retries + 1}/{self.max_retries + 1})")
        
        # Log task start to flow
        if flow_id:
            flow_logger = FlowLogger.from_flow_id(flow_id)
            if flow_logger and flow_logger.flow:
                flow_logger.log_event(
                    'EMAIL_TASK_STARTED',
                    status='info',
                    message=f"Celery task started for order {order_id}",
                    metadata={
                        'attempt': self.request.retries + 1,
                        'max_retries': self.max_retries + 1,
                        'task_id': self.request.id
                    }
                )
        
        # Call the optimized email sender
        result = send_experience_confirmation_email_optimized(
            order_id=order_id,
            to_email=to_email,
            flow_id=flow_id
        )
        
        if result['status'] == 'success':
            logger.info(f"✅ [CELERY_TASK_EXP] Email sent successfully for order {order_id}")
            return result
        elif result['status'] == 'skipped':
            logger.warning(f"⚠️ [CELERY_TASK_EXP] Email skipped for order {order_id}: {result.get('reason')}")
            return result
        else:
            # Email failed, raise exception to trigger retry
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"❌ [CELERY_TASK_EXP] Email failed for order {order_id}: {error_msg}")
            raise Exception(f"Email sending failed: {error_msg}")
        
    except Exception as exc:
        logger.error(f"❌ [CELERY_TASK_EXP] Error in email task for order {order_id}: {exc}", exc_info=True)
        
        # Log retry attempt to flow
        if flow_id:
            try:
                from core.flow_logger import FlowLogger
                flow_logger = FlowLogger.from_flow_id(flow_id)
                if flow_logger and flow_logger.flow:
                    flow_logger.log_event(
                        'EMAIL_TASK_RETRY',
                        status='warning',
                        message=f"Email task failed, retrying (attempt {self.request.retries + 1}/{self.max_retries + 1})",
                        metadata={
                            'error': str(exc),
                            'attempt': self.request.retries + 1,
                            'next_retry_in': self.default_retry_delay,
                        }
                    )
            except Exception as log_error:
                logger.error(f"❌ [CELERY_TASK_EXP] Failed to log retry to flow: {log_error}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = self.default_retry_delay * (2 ** self.request.retries)  # Exponential backoff
            logger.info(f"🔄 [CELERY_TASK_EXP] Retrying in {retry_delay} seconds...")
            raise self.retry(exc=exc, countdown=retry_delay)
        else:
            # Max retries reached, log final failure
            logger.error(f"❌ [CELERY_TASK_EXP] Max retries reached for order {order_id}, giving up")
            
            if flow_id:
                try:
                    from core.flow_logger import FlowLogger
                    flow_logger = FlowLogger.from_flow_id(flow_id)
                    if flow_logger and flow_logger.flow:
                        flow_logger.log_event(
                            'EMAIL_TASK_FAILED',
                            status='error',
                            message=f"Email task failed after {self.max_retries + 1} attempts",
                            metadata={
                                'error': str(exc),
                                'total_attempts': self.max_retries + 1,
                            }
                        )
                except Exception as log_error:
                    logger.error(f"❌ [CELERY_TASK_EXP] Failed to log final failure to flow: {log_error}")
            
            raise
