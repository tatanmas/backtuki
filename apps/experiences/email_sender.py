"""
🚀 ENTERPRISE Email Sender for Experiences - Tuki Platform
Analogous to apps/events/email_sender.py

Optimized email sending with <10s latency guarantee.

Performance:
- Pre-computed context (no queries in templates)
- Parallel processing when needed
- <10s total latency for typical order

Usage:
    from apps.experiences.email_sender import send_experience_confirmation_email_optimized
    
    result = send_experience_confirmation_email_optimized(order_id, flow_id=flow_id)
"""

import logging
import time
import os
from typing import Dict, Any, Optional
from django.conf import settings
from django.core.mail import get_connection
from django.template.loader import render_to_string
from django.utils import timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_experience_confirmation_email_optimized(
    order_id: str,
    to_email: Optional[str] = None,
    flow_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    🚀 ENTERPRISE: Send experience confirmation email with <10s latency.
    
    Reuses EXACTLY the same pattern as send_order_confirmation_email_optimized.
    
    Optimizations:
    - Pre-computed email context
    - No file I/O during send (except logos)
    - Detailed performance metrics
    
    Args:
        order_id: UUID of the order
        to_email: Optional override email address
        flow_id: Optional flow ID for tracking
        
    Returns:
        Dict with status, timing metrics, and results
        
    Performance: <10s for typical order
    """
    start_time = time.time()
    metrics = {
        'fetch_time_ms': 0,
        'context_time_ms': 0,
        'render_time_ms': 0,
        'smtp_time_ms': 0,
        'total_time_ms': 0,
    }
    
    try:
        from apps.events.models import Order, EmailLog
        from apps.experiences.email_context import build_experience_confirmation_context
        from core.flow_logger import FlowLogger
        
        # 1. Fetch order with optimized query
        fetch_start = time.time()
        order = Order.objects.select_related(
            'experience_reservation',
            'experience_reservation__experience',
            'experience_reservation__experience__organizer',
            'experience_reservation__instance',
            'experience_reservation__instance__language',
        ).prefetch_related(
            'experience_reservation__experience__images',
            'experience_reservation__resource_holds__resource',
        ).get(id=order_id)
        metrics['fetch_time_ms'] = int((time.time() - fetch_start) * 1000)
        
        logger.info(f"📧 [EMAIL_OPTIMIZED_EXP] Processing order {order.order_number} (fetched in {metrics['fetch_time_ms']}ms)")
        
        # Check order status
        if order.status != 'paid':
            logger.warning(f"📧 [EMAIL_OPTIMIZED_EXP] Order {order.order_number} not paid (status: {order.status}), skipping")
            return {'status': 'skipped', 'reason': 'order_not_paid', 'metrics': metrics}
        
        # Check order kind
        if order.order_kind != 'experience':
            logger.warning(f"📧 [EMAIL_OPTIMIZED_EXP] Order {order.order_number} is not an experience order (kind: {order.order_kind}), skipping")
            return {'status': 'skipped', 'reason': 'not_experience_order', 'metrics': metrics}
        
        # Get reservation
        reservation = order.experience_reservation
        if not reservation:
            logger.warning(f"📧 [EMAIL_OPTIMIZED_EXP] No reservation found for order {order.order_number}")
            return {'status': 'skipped', 'reason': 'no_reservation', 'metrics': metrics}
        
        # Determine recipient
        recipient_email = to_email or reservation.email
        
        logger.info(f"📧 [EMAIL_OPTIMIZED_EXP] Sending to {recipient_email} for reservation {reservation.reservation_id}")
        
        # 2. Build context (pre-computed, no queries)
        context_start = time.time()
        context = build_experience_confirmation_context(order, reservation)
        context_time = int((time.time() - context_start) * 1000)
        metrics['context_time_ms'] = context_time
        
        # 3. Render templates
        render_start = time.time()
        html_message = render_to_string('emails/experiences/confirmation.html', context)
        text_message = render_to_string('emails/experiences/confirmation.txt', context)
        render_time = int((time.time() - render_start) * 1000)
        metrics['render_time_ms'] = render_time
        
        logger.info(f"📧 [EMAIL_OPTIMIZED_EXP] Context built in {context_time}ms, rendered in {render_time}ms")
        
        # 4. Create email using proper MIME structure (same as events)
        # Structure: multipart/mixed -> multipart/alternative -> (text/plain | multipart/related -> text/html + images)
        subject = f"✅ Confirmación de reserva - {reservation.experience.title}"
        from_email = settings.DEFAULT_FROM_EMAIL
        
        # Create root message (multipart/mixed)
        root_msg = MIMEMultipart('mixed')
        root_msg['Subject'] = subject
        root_msg['From'] = from_email
        root_msg['To'] = recipient_email
        
        # Create multipart/alternative container for text and HTML
        alternative_msg = MIMEMultipart('alternative')
        
        # Add text version to alternative
        text_part = MIMEText(text_message, 'plain', 'utf-8')
        alternative_msg.attach(text_part)
        
        # Create multipart/related container for HTML and inline images
        # This prevents Apple Mail from showing images as separate attachments
        related_msg = MIMEMultipart('related')
        
        # Add HTML part to related container
        html_part = MIMEText(html_message, 'html', 'utf-8')
        related_msg.attach(html_part)
        
        # 5. Attach logos inline (same as events, NO QR codes for experiences)
        logo_negro_path = os.path.join(settings.BASE_DIR, 'static/images/logos/logo-negro.png')
        if os.path.exists(logo_negro_path):
            with open(logo_negro_path, 'rb') as logo_file:
                logo_negro = MIMEImage(logo_file.read())
                logo_negro.add_header('Content-ID', '<logo_negro>')
                # CRITICAL: No filename in Content-Disposition inline to prevent Apple Mail from showing as attachment
                logo_negro.add_header('Content-Disposition', 'inline')
                logo_negro.add_header('X-Attachment-Id', 'logo_negro')
                related_msg.attach(logo_negro)  # Attach to related, not root
        
        isotipo_path = os.path.join(settings.BASE_DIR, 'static/images/logos/isotipo-azul.png')
        if os.path.exists(isotipo_path):
            with open(isotipo_path, 'rb') as isotipo_file:
                isotipo_azul = MIMEImage(isotipo_file.read())
                isotipo_azul.add_header('Content-ID', '<isotipo_azul>')
                # CRITICAL: No filename in Content-Disposition inline to prevent Apple Mail from showing as attachment
                isotipo_azul.add_header('Content-Disposition', 'inline')
                isotipo_azul.add_header('X-Attachment-Id', 'isotipo_azul')
                related_msg.attach(isotipo_azul)  # Attach to related, not root
        
        # Attach the related container (HTML + images) to alternative
        alternative_msg.attach(related_msg)
        
        # Attach alternative to root
        root_msg.attach(alternative_msg)
        
        # 6. Create EmailLog (status='pending' primero)
        email_log = EmailLog.objects.create(
            order=order,
            to_email=recipient_email,
            subject=subject,
            template='experience_confirmation',
            status='pending',
            attempts=1,
            metadata={
                'reservation_id': reservation.reservation_id,
                'experience_title': reservation.experience.title,
                'participants': {
                    'adults': reservation.adult_count,
                    'children': reservation.child_count,
                    'infants': reservation.infant_count,
                }
            }
        )
        
        # 7. Send email using Django's connection with our custom MIME message (same wrapper as events)
        class MIMEWrapper:
            """Wrapper for MIMEMultipart that adds as_bytes() with linesep parameter"""
            def __init__(self, mime_message):
                self._mime_message = mime_message
            
            def as_bytes(self, linesep=None):
                """Convert MIME message to bytes, ignoring linesep parameter"""
                return self._mime_message.as_bytes()
            
            def __getattr__(self, name):
                """Delegate all other attributes to the wrapped MIME message"""
                return getattr(self._mime_message, name)
        
        class CustomEmailMessage:
            def __init__(self, mime_message, from_email, to_email):
                self._mime_message = MIMEWrapper(mime_message)
                self.from_email = from_email
                self.to = [to_email] if isinstance(to_email, str) else to_email
                self._recipients = self.to
                self.encoding = 'utf-8'
                self.cc = []
                self.bcc = []
                self.reply_to = []
                self.extra_headers = {}
                self.attachments = []
            
            def message(self):
                """Return the MIME message object"""
                return self._mime_message
            
            def recipients(self):
                """Return list of recipients - Django expects this as a method"""
                return self._recipients
            
            def get_connection(self, fail_silently):
                """Delegate to Django's connection getter"""
                return get_connection(fail_silently=fail_silently)
        
        custom_email = CustomEmailMessage(root_msg, from_email, recipient_email)
        
        # Send using Django's connection
        smtp_start = time.time()
        connection = get_connection(fail_silently=False)
        connection.send_messages([custom_email])
        smtp_time = int((time.time() - smtp_start) * 1000)
        metrics['smtp_time_ms'] = smtp_time
        
        # 8. Update EmailLog (status='sent', sent_at)
        email_log.status = 'sent'
        email_log.sent_at = timezone.now()
        email_log.save()
        
        logger.info(f"✅ [EMAIL_OPTIMIZED_EXP] Sent to {recipient_email} in {smtp_time}ms")
        
        # 9. Log to PlatformFlow (EMAIL_SENT event)
        if flow_id:
            flow_logger = FlowLogger.from_flow_id(flow_id)
            if flow_logger and flow_logger.flow:
                flow_logger.log_event(
                    'EMAIL_SENT',
                    order=order,
                    email_log=email_log,
                    status='success',
                    message=f"Email sent to {recipient_email}",
                    metadata={
                        'recipient': recipient_email,
                        'reservation_id': reservation.reservation_id,
                        'smtp_time_ms': smtp_time,
                        'context_time_ms': context_time,
                        'render_time_ms': render_time,
                    }
                )
        
        # 10. Return metrics
        metrics['total_time_ms'] = int((time.time() - start_time) * 1000)
        
        return {
            'status': 'success',
            'emails_sent': 1,
            'recipient': recipient_email,
            'metrics': metrics
        }
        
    except Exception as e:
        metrics['total_time_ms'] = int((time.time() - start_time) * 1000)
        logger.error(f"❌ [EMAIL_OPTIMIZED_EXP] Error sending email for order {order_id}: {e}", exc_info=True)
        
        # Log failure to flow
        if flow_id:
            try:
                from core.flow_logger import FlowLogger
                flow_logger = FlowLogger.from_flow_id(flow_id)
                if flow_logger and flow_logger.flow:
                    flow_logger.log_event(
                        'EMAIL_FAILED',
                        status='error',
                        message=f"Email sending failed: {str(e)}",
                        metadata={'error': str(e), 'metrics': metrics}
                    )
            except Exception as log_error:
                logger.error(f"❌ [EMAIL_OPTIMIZED_EXP] Failed to log error to flow: {log_error}")
        
        return {
            'status': 'error',
            'error': str(e),
            'metrics': metrics
        }
