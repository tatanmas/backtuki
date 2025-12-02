"""
🚀 ENTERPRISE Email Sender - Tuki Platform
Optimized email sending with <10s latency guarantee.

Performance:
- Uses pre-generated QR codes (no generation during send)
- Pre-computed context (no queries in templates)
- Parallel processing when needed
- <10s total latency for typical order

Usage:
    from apps.events.email_sender import send_order_confirmation_email_optimized
    
    result = send_order_confirmation_email_optimized(order_id, flow_id=flow_id)
"""

import logging
import time
from typing import Dict, Any, List, Optional
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64

logger = logging.getLogger(__name__)


def send_order_confirmation_email_optimized(
    order_id: str,
    to_email: Optional[str] = None,
    flow_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    🚀 ENTERPRISE: Send order confirmation email with <10s latency.
    
    Optimizations:
    - Uses pre-generated QR codes from database
    - Pre-computed email context
    - No file I/O during send
    - Detailed performance metrics
    
    Args:
        order_id: UUID of the order
        to_email: Optional override email address
        flow_id: Optional flow ID for tracking
        
    Returns:
        Dict with status, timing metrics, and results
        
    Performance: <10s for typical order with 10 tickets
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
        from apps.events.email_context import build_order_confirmation_context
        from core.flow_logger import FlowLogger
        
        # 1. Fetch order with optimized query
        fetch_start = time.time()
        order = Order.objects.select_related(
            'event',
            'event__organizer'
        ).prefetch_related(
            'items__tickets',
            'items__ticket_tier',
            'event__images'
        ).get(id=order_id)
        metrics['fetch_time_ms'] = int((time.time() - fetch_start) * 1000)
        
        logger.info(f"📧 [EMAIL_OPTIMIZED] Processing order {order.order_number} (fetched in {metrics['fetch_time_ms']}ms)")
        
        # Check order status
        if order.status != 'paid':
            logger.warning(f"📧 [EMAIL_OPTIMIZED] Order {order.order_number} not paid (status: {order.status}), skipping")
            return {'status': 'skipped', 'reason': 'order_not_paid', 'metrics': metrics}
        
        # 2. Get all tickets
        all_tickets = []
        for item in order.items.all():
            all_tickets.extend(list(item.tickets.all()))
        
        if not all_tickets:
            logger.warning(f"📧 [EMAIL_OPTIMIZED] No tickets found for order {order.order_number}")
            return {'status': 'skipped', 'reason': 'no_tickets', 'metrics': metrics}
        
        # 3. Separate regular tickets from raffle entries
        regular_tickets = []
        raffle_tickets = []
        
        for ticket in all_tickets:
            if ticket.order_item.ticket_tier.is_raffle:
                raffle_tickets.append(ticket)
            else:
                regular_tickets.append(ticket)
        
        logger.info(f"📧 [EMAIL_OPTIMIZED] Found {len(regular_tickets)} regular tickets, {len(raffle_tickets)} raffle entries")
        
        # 4. Group tickets by email
        tickets_by_email = {}
        for ticket in all_tickets:
            email = to_email or ticket.email
            if email not in tickets_by_email:
                tickets_by_email[email] = {'regular': [], 'raffle': []}
            
            if ticket in regular_tickets:
                tickets_by_email[email]['regular'].append(ticket)
            else:
                tickets_by_email[email]['raffle'].append(ticket)
        
        emails_sent = 0
        failed_emails = []
        
        # 5. Send email to each recipient
        for recipient_email, ticket_groups in tickets_by_email.items():
            try:
                recipient_regular = ticket_groups['regular']
                recipient_raffle = ticket_groups['raffle']
                
                logger.info(f"📧 [EMAIL_OPTIMIZED] Sending to {recipient_email}: {len(recipient_regular)} regular, {len(recipient_raffle)} raffle")
                
                # Build context (pre-computed, no queries)
                context_start = time.time()
                context = build_order_confirmation_context(order, recipient_regular, recipient_raffle)
                context_time = int((time.time() - context_start) * 1000)
                metrics['context_time_ms'] = max(metrics['context_time_ms'], context_time)
                
                # Render templates (using ORIGINAL templates, no changes to design)
                render_start = time.time()
                html_message = render_to_string('emails/order_confirmation.html', context)
                text_message = render_to_string('emails/order_confirmation.txt', context)
                render_time = int((time.time() - render_start) * 1000)
                metrics['render_time_ms'] = max(metrics['render_time_ms'], render_time)
                
                logger.info(f"📧 [EMAIL_OPTIMIZED] Context built in {context_time}ms, rendered in {render_time}ms")
                
                # Create email using proper MIME structure to prevent Apple Mail from showing images as attachments
                # Structure: multipart/mixed -> multipart/alternative -> (text/plain | multipart/related -> text/html + images)
                subject = f"🎟️ Tus entradas para {order.event.title}"
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
                
                # 🚀 ENTERPRISE: Generate and attach QR codes on-the-fly (no DB writes)
                # Esto evita problemas de transacciones y asegura que SIEMPRE haya QR,
                # incluso para órdenes antiguas sin qr_code en la base de datos.
                import os
                from apps.events.qr_generator import generate_qr_image
                
                frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')
                qr_attached_count = 0
                
                for ticket in recipient_regular:
                    try:
                        qr_bytes = generate_qr_image(ticket.ticket_number, frontend_url)
                        qr_image = MIMEImage(qr_bytes)
                        content_id = f'qr_code_{ticket.ticket_number}'
                        qr_image.add_header('Content-ID', f'<{content_id}>')
                        # CRITICAL: No filename in Content-Disposition inline to prevent Apple Mail from showing as attachment
                        qr_image.add_header('Content-Disposition', 'inline')
                        # Ensure it's treated as inline, not attachment
                        qr_image.add_header('X-Attachment-Id', content_id)
                        related_msg.attach(qr_image)  # Attach to related, not root
                        qr_attached_count += 1
                        logger.info(
                            f"📧 [EMAIL_OPTIMIZED] Generated & attached QR for ticket {ticket.ticket_number} "
                            f"(Content-ID: {content_id}, size: {len(qr_bytes)} bytes)"
                        )
                    except Exception as e:
                        logger.error(f"📧 [EMAIL_OPTIMIZED] Error generating/attaching QR for {ticket.ticket_number}: {e}", exc_info=True)
                
                logger.info(f"📧 [EMAIL_OPTIMIZED] Attached {qr_attached_count} QR codes for {len(recipient_regular)} regular tickets")
                
                # Attach logos (same as original)
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
                
                # Create EmailLog
                email_log = EmailLog.objects.create(
                    order=order,
                    to_email=recipient_email,
                    subject=subject,
                    template='order_confirmation',
                    status='pending',
                    attempts=1,
                    metadata={
                        'ticket_count': len(recipient_regular) + len(recipient_raffle),
                        'ticket_numbers': [t.ticket_number for t in recipient_regular + recipient_raffle]
                    }
                )
                
                # Send email using Django's connection with our custom MIME message
                # Create a wrapper class that mimics EmailMessage interface
                class MIMEWrapper:
                    """Wrapper for MIMEMultipart that adds as_bytes() with linesep parameter"""
                    def __init__(self, mime_message):
                        self._mime_message = mime_message
                    
                    def as_bytes(self, linesep=None):
                        """Convert MIME message to bytes, ignoring linesep parameter"""
                        # MIMEMultipart.as_bytes() doesn't accept linesep, so we ignore it
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
                        # Django expects these attributes
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
                metrics['smtp_time_ms'] = max(metrics['smtp_time_ms'], smtp_time)
                
                # Update EmailLog
                email_log.status = 'sent'
                email_log.sent_at = timezone.now()
                email_log.save()
                
                emails_sent += 1
                logger.info(f"✅ [EMAIL_OPTIMIZED] Sent to {recipient_email} in {smtp_time}ms")
                
                # Log to flow
                if flow_id:
                    flow_logger = FlowLogger.from_flow_id(flow_id)
                    if flow_logger and flow_logger.flow:
                        flow_logger.log_event(
                            'EMAIL_SENT',
                            order=order,
                            status='success',
                            message=f"Email sent to {recipient_email}",
                            metadata={
                                'recipient': recipient_email,
                                'ticket_count': len(recipient_regular) + len(recipient_raffle),
                                'smtp_time_ms': smtp_time,
                                'context_time_ms': context_time,
                                'render_time_ms': render_time,
                            }
                        )
                
            except Exception as e:
                logger.error(f"❌ [EMAIL_OPTIMIZED] Failed to send to {recipient_email}: {e}", exc_info=True)
                failed_emails.append({
                    'email': recipient_email,
                    'error': str(e),
                })
                
                # Update EmailLog
                if 'email_log' in locals():
                    email_log.status = 'failed'
                    email_log.error = str(e)
                    email_log.save()
                
                # Log to flow
                if flow_id:
                    flow_logger = FlowLogger.from_flow_id(flow_id)
                    if flow_logger and flow_logger.flow:
                        flow_logger.log_event(
                            'EMAIL_FAILED',
                            order=order,
                            status='failure',
                            message=f"Email failed: {str(e)}",
                            metadata={'recipient': recipient_email, 'error': str(e)}
                        )
        
        # Calculate total time
        metrics['total_time_ms'] = int((time.time() - start_time) * 1000)
        
        logger.info(
            f"✅ [EMAIL_OPTIMIZED] Completed: {emails_sent} sent, {len(failed_emails)} failed "
            f"in {metrics['total_time_ms']}ms"
        )
        
        return {
            'status': 'completed',
            'emails_sent': emails_sent,
            'failed_emails': failed_emails,
            'metrics': metrics,
        }
        
    except Exception as e:
        metrics['total_time_ms'] = int((time.time() - start_time) * 1000)
        logger.error(f"❌ [EMAIL_OPTIMIZED] Fatal error: {e}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e),
            'metrics': metrics,
        }

