"""
🚀 ENTERPRISE: Analytics Celery Tasks
Automated tasks for calculating and updating analytics metrics.
"""

from celery import shared_task
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Count, Sum, Avg, Q
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.core.files.base import ContentFile
import tempfile
import os
from apps.events.models import Event, TicketHolderReservation, TicketHold, Order
from apps.events.analytics_models import EventView, EventPerformanceMetrics, ConversionFunnel
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def calculate_daily_event_metrics(self, date_str=None):
    """
    🚀 ENTERPRISE: Calculate daily performance metrics for all events.
    
    This task runs daily to compute:
    - View metrics (total, unique, time on page)
    - Conversion metrics (rate, total conversions)
    - Revenue metrics (effective revenue, average order value)
    - Traffic source breakdown
    """
    try:
        # Parse date or use yesterday
        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            target_date = (timezone.now() - timedelta(days=1)).date()
        
        logger.info(f"[ANALYTICS] Starting daily metrics calculation for {target_date}")
        
        # Get all events that had activity on the target date
        events_with_activity = Event.objects.filter(
            Q(views__created_at__date=target_date) |
            Q(orders__created_at__date=target_date)
        ).distinct()
        
        metrics_created = 0
        metrics_updated = 0
        
        for event in events_with_activity:
            try:
                metrics = EventPerformanceMetrics.calculate_daily_metrics(event, target_date)
                
                if hasattr(metrics, '_state') and metrics._state.adding:
                    metrics_created += 1
                else:
                    metrics_updated += 1
                
                logger.debug(f"[ANALYTICS] Calculated metrics for event {event.id}: {event.title}")
                
            except Exception as e:
                logger.error(f"[ANALYTICS] Error calculating metrics for event {event.id}: {e}")
                continue
        
        logger.info(f"[ANALYTICS] Completed daily metrics: {metrics_created} created, {metrics_updated} updated")
        
        return {
            'date': target_date.isoformat(),
            'events_processed': len(events_with_activity),
            'metrics_created': metrics_created,
            'metrics_updated': metrics_updated
        }
        
    except Exception as exc:
        logger.error(f"[ANALYTICS] Error in calculate_daily_event_metrics: {exc}")
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=2)
def update_conversion_tracking(self, order_id):
    """
    🚀 ENTERPRISE: Update conversion tracking when an order is completed.
    
    This task runs when an order status changes to 'paid' to:
    - Mark related views as converted
    - Update funnel completion data
    - Calculate conversion timing
    """
    try:
        from apps.events.models import Order
        
        order = Order.objects.get(id=order_id)
        
        if order.status != 'paid':
            logger.warning(f"[ANALYTICS] Order {order_id} not paid, skipping conversion tracking")
            return
        
        # Find views that led to this conversion
        session_views = EventView.objects.filter(
            event=order.event,
            session_id=order.user_agent  # Assuming session tracking
        ).order_by('created_at')
        
        if session_views.exists():
            # Mark the first view as converted
            first_view = session_views.first()
            first_view.converted_to_purchase = True
            first_view.conversion_order = order
            first_view.save(update_fields=['converted_to_purchase', 'conversion_order'])
            
            # Update funnel completion
            ConversionFunnel.objects.filter(
                event=order.event,
                session_id=first_view.session_id,
                stage='purchase_complete'
            ).update(order=order)
            
            logger.info(f"[ANALYTICS] Updated conversion tracking for order {order_id}")
        
        return {
            'order_id': order_id,
            'event_id': str(order.event.id),
            'views_updated': session_views.count()
        }
        
    except Exception as exc:
        logger.error(f"[ANALYTICS] Error in update_conversion_tracking: {exc}")
        self.retry(countdown=30 * (self.request.retries + 1))


@shared_task
def cleanup_old_analytics_data():
    """
    🚀 ENTERPRISE: Clean up old analytics data to maintain performance.
    
    Removes:
    - Event views older than 2 years
    - Conversion funnel data older than 1 year
    - Performance metrics older than 3 years
    """
    try:
        cutoff_views = timezone.now() - timedelta(days=730)  # 2 years
        cutoff_funnel = timezone.now() - timedelta(days=365)  # 1 year
        cutoff_metrics = timezone.now() - timedelta(days=1095)  # 3 years
        
        # Clean up old views
        deleted_views = EventView.objects.filter(
            created_at__lt=cutoff_views
        ).delete()
        
        # Clean up old funnel data
        deleted_funnel = ConversionFunnel.objects.filter(
            created_at__lt=cutoff_funnel
        ).delete()
        
        # Clean up old metrics
        deleted_metrics = EventPerformanceMetrics.objects.filter(
            date__lt=cutoff_metrics.date()
        ).delete()
        
        logger.info(f"[ANALYTICS] Cleanup completed: {deleted_views[0]} views, {deleted_funnel[0]} funnel records, {deleted_metrics[0]} metrics")
        
        return {
            'views_deleted': deleted_views[0],
            'funnel_deleted': deleted_funnel[0],
            'metrics_deleted': deleted_metrics[0]
        }
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Error in cleanup_old_analytics_data: {e}")
        raise


@shared_task
def generate_weekly_analytics_report():
    """
    🚀 ENTERPRISE: Generate weekly analytics summary for organizers.
    
    Creates summary reports with:
    - Top performing events
    - Conversion trends
    - Revenue insights
    - Traffic source analysis
    """
    try:
        from django.core.mail import send_mail
        from django.template.loader import render_to_string
        from apps.organizers.models import Organizer
        
        week_start = timezone.now() - timedelta(days=7)
        
        # Get all active organizers
        organizers = Organizer.objects.filter(is_active=True)
        
        reports_sent = 0
        
        for organizer in organizers:
            try:
                # Calculate weekly metrics for organizer
                events = organizer.events.all()
                
                weekly_metrics = EventPerformanceMetrics.objects.filter(
                    event__in=events,
                    date__gte=week_start.date()
                ).aggregate(
                    total_views=Sum('total_views'),
                    total_conversions=Sum('total_conversions'),
                    total_revenue=Sum('total_revenue'),
                    avg_conversion_rate=Avg('conversion_rate')
                )
                
                if weekly_metrics['total_views']:
                    # Generate and send report
                    context = {
                        'organizer': organizer,
                        'week_start': week_start,
                        'metrics': weekly_metrics,
                        'top_events': events.order_by('-performance_metrics__total_revenue')[:5]
                    }
                    
                    # This would render an email template
                    # email_html = render_to_string('emails/weekly_analytics_report.html', context)
                    
                    # For now, just log
                    logger.info(f"[ANALYTICS] Weekly report generated for organizer {organizer.id}")
                    reports_sent += 1
                
            except Exception as e:
                logger.error(f"[ANALYTICS] Error generating report for organizer {organizer.id}: {e}")
                continue
        
        return {
            'reports_sent': reports_sent,
            'week_start': week_start.isoformat()
        }
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Error in generate_weekly_analytics_report: {e}")
        raise


@shared_task
def update_event_view_metrics(event_id, session_id, time_on_page):
    """
    🚀 ENTERPRISE: Update time on page for an event view.
    
    Called when user leaves the page to record actual time spent.
    """
    try:
        view = EventView.objects.filter(
            event_id=event_id,
            session_id=session_id
        ).order_by('-created_at').first()
        
        if view and not view.time_on_page:
            view.time_on_page = time_on_page
            view.save(update_fields=['time_on_page'])
            
            logger.debug(f"[ANALYTICS] Updated time on page for view {view.id}: {time_on_page}s")
            
            return {'view_id': view.id, 'time_on_page': time_on_page}
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Error updating view metrics: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def send_ticket_confirmation_email(self, order_id):
    """
    🚀 ENTERPRISE: Send ticket confirmation email to customer.
    
    Sends a confirmation email with ticket details after successful booking.
    """
    try:
        from django.conf import settings
        
        from apps.events.models import Order
        
        logger.info(f"📧 [EMAIL] Starting ticket confirmation email for order: {order_id}")
        
        # Get the order with related data
        logger.info(
            "📧 [EMAIL] DEBUG: About to execute query - "
            "select_related('event', 'event__organizer'), NO 'user'"
        )
        try:
            order = Order.objects.select_related(
                'event',
                'event__organizer',
            ).prefetch_related('items__tickets').get(id=order_id)
            logger.info(
                f"📧 [EMAIL] DEBUG: ✅ Order fetched successfully - Status: {order.status}"
            )
        except Exception as query_error:
            logger.error(
                f"📧 [EMAIL] DEBUG: ❌ ERROR in query execution: {type(query_error).__name__}: {query_error}"
            )
            logger.error(
                f"📧 [EMAIL] DEBUG: Query error details: {str(query_error)}"
            )
            import traceback

            logger.error(
                f"📧 [EMAIL] DEBUG: Traceback: {traceback.format_exc()}"
            )
            raise
        
        if order.status != 'paid':
            logger.warning(f"📧 [EMAIL] Order {order_id} not paid (status: {order.status}), skipping email")
            return {'status': 'skipped', 'reason': 'order_not_paid'}
        
        # Get all tickets from all order items
        tickets = []
        for item in order.items.all():
            tickets.extend(item.tickets.all())
        
        if not tickets:
            logger.warning(f"📧 [EMAIL] No tickets found for order {order_id}")
            return {'status': 'skipped', 'reason': 'no_tickets'}
        
        # Send one email per ticket (professional ticketing approach)
        emails_sent = 0
        failed_emails = []
        
        for ticket in tickets:
            qr_temp_file = None
            try:
                # Import QRCodeService
                from apps.events.services import QRCodeService
                import qrcode
                from io import BytesIO
                
                # Generate QR code as file (not base64) for inline embedding
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_H,
                    box_size=10,
                    border=4,
                )
                
                # QR data with ticket URL
                qr_data = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')}/tickets/{ticket.ticket_number}"
                qr.add_data(qr_data)
                qr.make(fit=True)
                
                # Create high-quality QR image
                img = qr.make_image(fill_color="black", back_color="white")
                
                # Save to temporary file
                qr_temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                img.save(qr_temp_file.name, format='PNG')
                qr_temp_file.close()
                
                # Prepare email context for this specific ticket
                context = {
                    'order': order,
                    'event': order.event,
                    'ticket': ticket,  # Single ticket (what template expects)
                    'attendee_name': f"{ticket.first_name} {ticket.last_name}".strip(),
                    'organizer': order.event.organizer,
                    'total_amount': order.total,
                    'booking_date': order.created_at,
                    'frontend_url': getattr(settings, 'FRONTEND_URL', 'http://localhost:8080'),
                    'qr_code': 'cid:qr_code',  # Reference to inline image
                    'qr_code_url': qr_data,
                }
                
                # Render email templates (default to minimal_professional)
                template_version = getattr(settings, 'EMAIL_TEMPLATE_VERSION', 'minimal_professional')
                html_template = f'emails/confirmation/{template_version}.html'
                
                # Fallback to original template if version doesn't exist
                try:
                    html_message = render_to_string(html_template, context)
                except:
                    html_message = render_to_string('emails/ticket_confirmation.html', context)
                
                text_message = render_to_string('emails/ticket_confirmation.txt', context)
                
                # Create email with inline QR code
                subject = f'Tu ticket para {order.event.title} - #{ticket.ticket_number}'
                recipient_email = ticket.email
                
                # Use EmailMultiAlternatives for inline images
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[recipient_email]
                )
                
                # Attach HTML version
                email.attach_alternative(html_message, "text/html")
                
                # Attach QR code as inline image with Content-ID
                with open(qr_temp_file.name, 'rb') as qr_file:
                    qr_content = qr_file.read()
                
                # Create MIMEImage for inline attachment
                from email.mime.image import MIMEImage
                qr_image = MIMEImage(qr_content)
                qr_image.add_header('Content-ID', '<qr_code>')
                qr_image.add_header('Content-Disposition', 'inline', filename=f'qr_code_{ticket.ticket_number}.png')
                
                # Attach logos as inline images
                import os
                
                
                # Logo negro para ticket
                logo_negro_path = os.path.join(settings.BASE_DIR, 'static/images/logos/logo-negro.png')
                if os.path.exists(logo_negro_path):
                    with open(logo_negro_path, 'rb') as logo_file:
                        logo_negro = MIMEImage(logo_file.read())
                        logo_negro.add_header('Content-ID', '<logo_negro>')
                        logo_negro.add_header('Content-Disposition', 'inline', filename='logo-negro.png')
                        email.attach(logo_negro)
                
                # Isotipo azul para footer
                isotipo_path = os.path.join(settings.BASE_DIR, 'static/images/logos/isotipo-azul.png')
                if os.path.exists(isotipo_path):
                    with open(isotipo_path, 'rb') as isotipo_file:
                        isotipo_azul = MIMEImage(isotipo_file.read())
                        isotipo_azul.add_header('Content-ID', '<isotipo_azul>')
                        isotipo_azul.add_header('Content-Disposition', 'inline', filename='isotipo-azul.png')
                        email.attach(isotipo_azul)
                
                # Attach QR code to email
                email.attach(qr_image)
                
                # Send email
                email.send(fail_silently=False)
                
                emails_sent += 1
                logger.info(f"📧 [EMAIL] Ticket email with inline QR sent for ticket {ticket.ticket_number} to {recipient_email}")
                
            except Exception as e:
                logger.error(f"📧 [EMAIL] Failed to send email for ticket {ticket.ticket_number}: {e}")
                failed_emails.append({
                    'ticket_number': ticket.ticket_number,
                    'email': ticket.email,
                    'error': str(e)
                })
                continue
            finally:
                # Clean up temporary file
                if qr_temp_file and os.path.exists(qr_temp_file.name):
                    try:
                        os.unlink(qr_temp_file.name)
                    except Exception as cleanup_error:
                        logger.warning(f"📧 [EMAIL] Failed to cleanup temp QR file: {cleanup_error}")
        
        logger.info(f"📧 [EMAIL] Ticket confirmation emails completed for order: {order_id} - {emails_sent} sent, {len(failed_emails)} failed")
        
        return {
            'status': 'sent' if emails_sent > 0 else 'failed',
            'order_id': order_id,
            'emails_sent': emails_sent,
            'failed_emails': failed_emails,
            'total_tickets': len(tickets)
        }
        
    except Order.DoesNotExist:
        logger.error(f"📧 [EMAIL] Order {order_id} not found")
        return {'status': 'error', 'reason': 'order_not_found'}
        
    except Exception as exc:
        logger.error(f"📧 [EMAIL] Error sending ticket confirmation email for order {order_id}: {exc}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
            logger.info(f"📧 [EMAIL] Retrying in {countdown}s (attempt {self.request.retries + 1}/{self.max_retries})")
            self.retry(countdown=countdown)
        else:
            logger.error(f"📧 [EMAIL] Max retries reached for order {order_id}, giving up")
            return {'status': 'failed', 'reason': str(exc)}


@shared_task
def cleanup_expired_ticket_holds():
    """
    🚀 ENTERPRISE: Clean up expired ticket holds.
    
    Removes expired ticket reservations to free up inventory.
    This task runs every 5 minutes via Celery Beat.
    """
    try:
        from apps.events.models import TicketHold
        from django.utils import timezone
        
        # Get expired holds (older than 15 minutes)
        expiry_time = timezone.now() - timezone.timedelta(minutes=15)
        
        expired_holds = TicketHold.objects.filter(
            expires_at__lt=timezone.now(),
            released=False
        )
        
        count = expired_holds.count()
        
        if count > 0:
            # Mark as released and free up the holds
            expired_holds.update(released=True)
            logger.info(f"🧹 [CLEANUP] Cleaned up {count} expired ticket holds")
        
        return {
            'cleaned_holds': count,
            'expiry_time': expiry_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"🧹 [CLEANUP] Error in cleanup_expired_ticket_holds: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def cleanup_expired_ticket_holder_reservations(self, hours_old=24):
    """
    🚀 ENTERPRISE: Clean up expired ticket holder reservations
    
    This task removes TicketHolderReservation records for orders that:
    - Are older than specified hours
    - Have status 'pending' (never completed payment)
    - Are not associated with successful payments
    
    Args:
        hours_old (int): Hours after which to consider reservations expired (default: 24)
    """
    try:
        expiry_time = timezone.now() - timedelta(hours=hours_old)
        logger.info(f"🧹 [CLEANUP] Starting cleanup of ticket holder reservations older than {expiry_time}")
        
        # Find expired reservations for pending orders
        expired_reservations = TicketHolderReservation.objects.filter(
            created_at__lt=expiry_time,
            order__status='pending'  # Only clean up unpaid orders
        ).select_related('order')
        
        count = expired_reservations.count()
        
        if count > 0:
            # Get order IDs for logging
            order_ids = list(expired_reservations.values_list('order_id', flat=True).distinct())
            
            # Delete expired reservations
            expired_reservations.delete()
            
            logger.info(f"🧹 [CLEANUP] Cleaned up {count} expired ticket holder reservations for {len(order_ids)} orders")
            logger.info(f"🧹 [CLEANUP] Affected orders: {order_ids[:10]}{'...' if len(order_ids) > 10 else ''}")
        
        return {
            'cleaned_reservations': count,
            'expiry_time': expiry_time.isoformat(),
            'affected_orders': len(set(expired_reservations.values_list('order_id', flat=True))) if count > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"🧹 [CLEANUP] Error in cleanup_expired_ticket_holder_reservations: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def cleanup_abandoned_orders(self, hours_old=48):
    """
    🚀 ENTERPRISE: Clean up completely abandoned orders
    
    This task removes Order records that:
    - Are older than specified hours
    - Have status 'pending' (never completed payment)
    - Have no associated tickets or successful payments
    
    Args:
        hours_old (int): Hours after which to consider orders abandoned (default: 48)
    """
    try:
        expiry_time = timezone.now() - timedelta(hours=hours_old)
        logger.info(f"🧹 [CLEANUP] Starting cleanup of abandoned orders older than {expiry_time}")
        
        # Find abandoned orders
        abandoned_orders = Order.objects.filter(
            created_at__lt=expiry_time,
            status='pending',
            # Ensure no successful tickets were created
            items__tickets__isnull=True
        ).distinct()
        
        count = abandoned_orders.count()
        
        if count > 0:
            order_ids = list(abandoned_orders.values_list('id', flat=True))
            
            # Clean up related data first
            TicketHolderReservation.objects.filter(order__in=abandoned_orders).delete()
            TicketHold.objects.filter(order__in=abandoned_orders).delete()
            
            # Delete the orders
            abandoned_orders.delete()
            
            logger.info(f"🧹 [CLEANUP] Cleaned up {count} abandoned orders")
            logger.info(f"🧹 [CLEANUP] Deleted order IDs: {order_ids[:10]}{'...' if len(order_ids) > 10 else ''}")
        
        return {
            'cleaned_orders': count,
            'expiry_time': expiry_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"🧹 [CLEANUP] Error in cleanup_abandoned_orders: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def send_order_confirmation_email(self, order_id, to_email=None):
    """
    🚀 ENTERPRISE: Send consolidated order confirmation email to customer.
    
    Sends a single confirmation email with all tickets for the order.
    
    Args:
        order_id: UUID of the order
        to_email: Optional email address to send to (overrides ticket emails)
    """
    try:
        from django.conf import settings
        from django.utils import timezone
        from apps.events.models import Order, EmailLog
        
        import tempfile
        import os
        
        logger.info(f"📧 [EMAIL] Starting order confirmation email for order: {order_id}")
        
        # DEBUG: Verify User model doesn't have organizer field
        from apps.users.models import User
        has_organizer_field = hasattr(User, 'organizer') or 'organizer' in [f.name for f in User._meta.get_fields()]
        logger.info(f"📧 [EMAIL] DEBUG: User model has 'organizer' field: {has_organizer_field}")
        if has_organizer_field:
            logger.error(f"📧 [EMAIL] DEBUG: ⚠️⚠️⚠️ PROBLEM: User model still has 'organizer' field defined! This will cause SQL errors!")
            logger.error(f"📧 [EMAIL] DEBUG: User model fields: {[f.name for f in User._meta.get_fields() if hasattr(f, 'name')]}")
        
        # DEBUG: Log Django query that will be executed
        from django.db import connection
        connection.queries_log.clear()
        
        logger.info(f"📧 [EMAIL] DEBUG: Fetching order data for {order_id}")
        logger.info(f"📧 [EMAIL] DEBUG: About to execute query - select_related('event', 'event__organizer'), NO 'user'")
        logger.info(f"📧 [EMAIL] DEBUG: Code version check - select_related does NOT include 'user'")
        
        # DEBUG: Verify Order model user field
        from apps.events.models import Order
        order_user_field = Order._meta.get_field('user')
        logger.info(f"📧 [EMAIL] DEBUG: Order.user field type: {type(order_user_field)}, related_model: {order_user_field.related_model}")
        
        try:
            # Build queryset
            queryset = Order.objects.select_related('event', 'event__organizer').prefetch_related('items__tickets', 'event__images')
            logger.info(f"📧 [EMAIL] DEBUG: Queryset built, about to execute .get(id={order_id})")
            
            # Execute query
            order = queryset.get(id=order_id)
            
            # Log SQL queries executed
            if connection.queries:
                logger.info(f"📧 [EMAIL] DEBUG: SQL queries executed ({len(connection.queries)} queries):")
                for i, query in enumerate(connection.queries[-3:], 1):  # Last 3 queries
                    logger.info(f"📧 [EMAIL] DEBUG:   Query {i}: {query['sql'][:200]}...")
            
            logger.info(f"📧 [EMAIL] DEBUG: ✅ Order fetched successfully - Status: {order.status}, Event: {order.event.title}")
            logger.info(f"📧 [EMAIL] DEBUG: Order.user_id (FK): {order.user_id if hasattr(order, 'user_id') else 'NO ATTR'}")
            
            # CRITICAL: Do NOT access order.user here, it would trigger lazy loading
            logger.info(f"📧 [EMAIL] DEBUG: NOT accessing order.user to avoid lazy loading")
            
        except Exception as query_error:
            logger.error(f"📧 [EMAIL] DEBUG: ❌ ERROR in query execution: {type(query_error).__name__}: {query_error}")
            logger.error(f"📧 [EMAIL] DEBUG: Query error details: {str(query_error)}")
            
            # Log SQL queries that were attempted
            if connection.queries:
                logger.error(f"📧 [EMAIL] DEBUG: SQL queries attempted before error ({len(connection.queries)} queries):")
                for i, query in enumerate(connection.queries[-5:], 1):  # Last 5 queries
                    logger.error(f"📧 [EMAIL] DEBUG:   Failed Query {i}: {query['sql'][:300]}...")
            
            import traceback
            logger.error(f"📧 [EMAIL] DEBUG: Full traceback: {traceback.format_exc()}")
            raise
        
        if order.status != 'paid':
            logger.warning(f"📧 [EMAIL] Order {order_id} not paid (status: {order.status}), skipping email")
            return {'status': 'skipped', 'reason': 'order_not_paid'}
        
        # Get all tickets from all order items
        logger.info(f"📧 [EMAIL] DEBUG: Fetching tickets for order {order_id}")
        tickets = []
        for item in order.items.all():
            tickets.extend(item.tickets.all())
        logger.info(f"📧 [EMAIL] DEBUG: Found {len(tickets)} tickets")
        
        if not tickets:
            logger.warning(f"📧 [EMAIL] No tickets found for order {order_id}")
            return {'status': 'skipped', 'reason': 'no_tickets'}
        
        # Group tickets by email to send one email per recipient
        logger.info(f"📧 [EMAIL] DEBUG: Grouping tickets by email")
        tickets_by_email = {}
        for ticket in tickets:
            # Use provided email or ticket email
            email = to_email or ticket.email
            if email not in tickets_by_email:
                tickets_by_email[email] = []
            tickets_by_email[email].append(ticket)
        logger.info(f"📧 [EMAIL] DEBUG: Grouped into {len(tickets_by_email)} email recipients")
        
        emails_sent = 0
        failed_emails = []
        
        for recipient_email, recipient_tickets in tickets_by_email.items():
            logger.info(f"📧 [EMAIL] DEBUG: Processing email for {recipient_email} with {len(recipient_tickets)} tickets")
            qr_temp_files = []
            try:
                # Generate QR codes for all tickets for this recipient
                logger.info(f"📧 [EMAIL] DEBUG: Starting QR code generation for {recipient_email}")
                import qrcode
                
                for ticket in recipient_tickets:
                    # Generate QR code as file for inline embedding
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_H,
                        box_size=10,
                        border=4,
                    )
                    
                    # QR data with ticket URL
                    qr_data = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')}/tickets/{ticket.ticket_number}"
                    qr.add_data(qr_data)
                    qr.make(fit=True)
                    
                    # Create high-quality QR image
                    img = qr.make_image(fill_color="black", back_color="white")
                    
                    # Save to temporary file
                    qr_temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                    img.save(qr_temp_file.name, format='PNG')
                    qr_temp_file.close()
                    qr_temp_files.append((qr_temp_file.name, ticket.ticket_number))
                
                logger.info(f"📧 [EMAIL] DEBUG: QR codes generated successfully for {recipient_email}")
                
                # Prepare email context for this recipient's tickets
                logger.info(f"📧 [EMAIL] DEBUG: Preparing email context for {recipient_email}")
                context = {
                    'order': order,
                    'event': order.event,
                    'tickets': recipient_tickets,  # All tickets for this recipient
                    'attendee_name': f"{recipient_tickets[0].first_name} {recipient_tickets[0].last_name}".strip(),
                    'organizer': order.event.organizer,
                    'total_amount': order.total,
                    'booking_date': order.created_at,
                    'frontend_url': getattr(settings, 'FRONTEND_URL', 'http://localhost:8080'),
                }
                
                # Render email templates (use order confirmation template with fallback)
                logger.info(f"📧 [EMAIL] DEBUG: Starting template rendering for {recipient_email}")
                try:
                    logger.info(f"📧 [EMAIL] DEBUG: Rendering HTML template order_confirmation.html")
                    html_message = render_to_string('emails/order_confirmation.html', context)
                    logger.info(f"📧 [EMAIL] Successfully rendered order confirmation HTML template")
                except Exception as e:
                    logger.warning(f"📧 [EMAIL] Order confirmation HTML template failed, using fallback: {e}")
                    logger.info(f"📧 [EMAIL] DEBUG: Rendering fallback HTML template ticket_confirmation.html")
                    # Fallback to existing template
                    html_message = render_to_string('emails/ticket_confirmation.html', context)
                    logger.info(f"📧 [EMAIL] DEBUG: Fallback HTML template rendered successfully")
                
                try:
                    logger.info(f"📧 [EMAIL] DEBUG: Rendering text template order_confirmation.txt")
                    text_message = render_to_string('emails/order_confirmation.txt', context)
                    logger.info(f"📧 [EMAIL] Successfully rendered order confirmation text template")
                except Exception as e:
                    logger.warning(f"📧 [EMAIL] Order confirmation text template failed, using fallback: {e}")
                    logger.info(f"📧 [EMAIL] DEBUG: Rendering fallback text template ticket_confirmation.txt")
                    # Fallback to existing template
                    text_message = render_to_string('emails/ticket_confirmation.txt', context)
                    logger.info(f"📧 [EMAIL] DEBUG: Fallback text template rendered successfully")
                
                # Create email with inline QR codes
                logger.info(f"📧 [EMAIL] DEBUG: Creating email message for {recipient_email}")
                subject = f'Tu orden para {order.event.title} - {len(recipient_tickets)} ticket{"s" if len(recipient_tickets) > 1 else ""}'
                
                # Use EmailMultiAlternatives for inline images
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[recipient_email]
                )
                
                # Attach HTML version
                email.attach_alternative(html_message, "text/html")
                logger.info(f"📧 [EMAIL] DEBUG: Email message created, attaching QR codes")
                
                # Attach QR codes as inline images
                from email.mime.image import MIMEImage
                for qr_file_path, ticket_number in qr_temp_files:
                    with open(qr_file_path, 'rb') as qr_file:
                        qr_content = qr_file.read()
                    
                    qr_image = MIMEImage(qr_content)
                    qr_image.add_header('Content-ID', f'<qr_code_{ticket_number}>')
                    qr_image.add_header('Content-Disposition', 'inline', filename=f'qr_code_{ticket_number}.png')
                    email.attach(qr_image)
                
                # Attach logos as inline images
                logo_negro_path = os.path.join(settings.BASE_DIR, 'static/images/logos/logo-negro.png')
                if os.path.exists(logo_negro_path):
                    with open(logo_negro_path, 'rb') as logo_file:
                        logo_negro = MIMEImage(logo_file.read())
                        logo_negro.add_header('Content-ID', '<logo_negro>')
                        logo_negro.add_header('Content-Disposition', 'inline', filename='logo-negro.png')
                        email.attach(logo_negro)
                
                # Isotipo azul para footer
                isotipo_path = os.path.join(settings.BASE_DIR, 'static/images/logos/isotipo-azul.png')
                if os.path.exists(isotipo_path):
                    with open(isotipo_path, 'rb') as isotipo_file:
                        isotipo_azul = MIMEImage(isotipo_file.read())
                        isotipo_azul.add_header('Content-ID', '<isotipo_azul>')
                        isotipo_azul.add_header('Content-Disposition', 'inline', filename='isotipo-azul.png')
                        email.attach(isotipo_azul)
                
                # Create EmailLog entry before sending
                email_log = EmailLog.objects.create(
                    order=order,
                    to_email=recipient_email,
                    subject=subject,
                    template='order_confirmation',
                    status='pending',
                    attempts=1,
                    metadata={'ticket_count': len(recipient_tickets), 'ticket_numbers': [t.ticket_number for t in recipient_tickets]}
                )
                
                # Send email
                logger.info(f"📧 [EMAIL] Attempting to send email to {recipient_email}")
                logger.info(f"📧 [EMAIL] DEBUG: About to call email.send()")
                try:
                    email.send()
                    logger.info(f"📧 [EMAIL] DEBUG: email.send() completed successfully")
                    
                    # Update EmailLog on success
                    email_log.status = 'sent'
                    email_log.sent_at = timezone.now()
                    email_log.save()
                    
                    emails_sent += 1
                    logger.info(f"📧 [EMAIL] ✅ Order confirmation sent to {recipient_email} for {len(recipient_tickets)} tickets")
                except Exception as send_error:
                    # Update EmailLog on failure
                    email_log.status = 'failed'
                    email_log.error = str(send_error)
                    email_log.attempts += 1
                    email_log.save()
                    raise send_error
                
            except Exception as e:
                logger.error(f"📧 [EMAIL] Failed to send order confirmation to {recipient_email}: {e}")
                failed_emails.append({
                    'email': recipient_email,
                    'error': str(e),
                    'tickets': [t.ticket_number for t in recipient_tickets]
                })
            finally:
                # Clean up temporary QR files
                for qr_file_path, _ in qr_temp_files:
                    try:
                        os.unlink(qr_file_path)
                    except:
                        pass
        
        logger.info(f"📧 [EMAIL] Order confirmation completed: {emails_sent} sent, {len(failed_emails)} failed")
        
        return {
            'status': 'completed',
            'emails_sent': emails_sent,
            'failed_emails': failed_emails,
            'total_tickets': len(tickets)
        }
        
    except Exception as e:
        logger.error(f"📧 [EMAIL] Error in send_order_confirmation_email: {e}")
        self.retry(countdown=60 * (self.request.retries + 1), exc=e)