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


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def notify_creator_on_sale(self, reservation_id: str):
    """
    Notify creator by email when a reservation paid with their link is confirmed.
    """
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        from apps.experiences.models import ExperienceReservation

        reservation = ExperienceReservation.objects.select_related(
            'creator', 'creator__user', 'experience', 'instance'
        ).filter(id=reservation_id).first()
        if not reservation or not reservation.creator_id:
            logger.info(f"[CREATOR_NOTIFY] Reservation {reservation_id} has no creator, skip")
            return {'status': 'skipped', 'reason': 'no_creator'}
        email = getattr(reservation.creator.user, 'email', None)
        if not email:
            logger.warning(f"[CREATOR_NOTIFY] Creator {reservation.creator_id} has no user email, skip")
            return {'status': 'skipped', 'reason': 'no_creator_email'}

        exp_title = reservation.experience.title if reservation.experience_id else 'Experiencia'
        date_str = ''
        if getattr(reservation.instance, 'start_datetime', None):
            date_str = reservation.instance.start_datetime.strftime('%d/%m/%Y %H:%M')

        subject = f"Alguien reservó con tu link: {exp_title}"
        body = f"Hola,\n\nAlguien reservó con tu link de creador.\n\n"
        body += f"Experiencia: {exp_title}\n"
        if date_str:
            body += f"Fecha: {date_str}\n"
        body += "\nSigue compartiendo tus links para seguir generando comisiones.\n\n— TUKI"

        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        logger.info(f"[CREATOR_NOTIFY] Email sent to creator for reservation {reservation.reservation_id}")
        return {'status': 'success'}
    except Exception as exc:
        logger.exception(f"[CREATOR_NOTIFY] Failed to notify creator for reservation {reservation_id}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=self.default_retry_delay * (2 ** self.request.retries))
        raise


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_review_invite_email(self, reservation_id: str):
    """
    Send email to customer with unique link to review form after reservation marked as attended.
    Sets review_token on reservation if not already set.
    """
    try:
        import uuid as uuid_module
        from django.core.mail import send_mail
        from django.conf import settings
        from apps.experiences.models import ExperienceReservation

        reservation = ExperienceReservation.objects.select_related(
            'experience', 'instance',
        ).filter(id=reservation_id).first()
        if not reservation:
            logger.warning(f"[REVIEW_INVITE] Reservation {reservation_id} not found")
            return {'status': 'skipped', 'reason': 'not_found'}
        if not reservation.email:
            logger.warning(f"[REVIEW_INVITE] Reservation {reservation_id} has no email")
            return {'status': 'skipped', 'reason': 'no_email'}
        if getattr(reservation, 'review', None):
            logger.info(f"[REVIEW_INVITE] Reservation {reservation_id} already has a review")
            return {'status': 'skipped', 'reason': 'already_reviewed'}

        if not reservation.review_token:
            reservation.review_token = uuid_module.uuid4()
            reservation.save(update_fields=['review_token', 'updated_at'])

        frontend_base = getattr(settings, 'FRONTEND_BASE_URL', 'https://tuki.cl') or 'https://tuki.cl'
        review_url = f"{frontend_base.rstrip('/')}/review?token={reservation.review_token}"

        exp_title = reservation.experience.title if reservation.experience_id else 'tu experiencia'
        subject = f"¿Cómo fue tu experiencia? Cuéntanos — {exp_title}"
        body = f"Hola,\n\n"
        body += f"Esperamos que hayas disfrutado {exp_title}.\n\n"
        body += "Tu opinión ayuda a otros viajeros. ¿Podrías dejarnos una reseña?\n\n"
        body += f"Compartir tu experiencia (solo toma un minuto):\n{review_url}\n\n"
        body += "Gracias,\n— TUKI"

        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reservation.email],
            fail_silently=False,
        )
        logger.info(f"[REVIEW_INVITE] Review invite sent for reservation {reservation.reservation_id}")
        return {'status': 'success'}
    except Exception as exc:
        logger.exception(f"[REVIEW_INVITE] Failed for reservation {reservation_id}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=self.default_retry_delay * (2 ** self.request.retries))
        raise
