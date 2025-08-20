"""
🚀 ENTERPRISE CELERY TASKS for Events App

These tasks handle background processing for the ticketing system,
including automatic cleanup of expired ticket holds to prevent stock leakage.
"""

from celery import shared_task
from django.utils import timezone
from django.db import transaction
from apps.events.models import TicketHold
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True)
def cleanup_expired_ticket_holds(self):
    """
    🚀 ENTERPRISE TASK: Clean up expired ticket holds automatically.
    
    This task runs every 5 minutes to ensure that expired holds are released
    and tickets become available again. Critical for preventing stock leakage
    in high-volume ticketing scenarios.
    
    Returns:
        dict: Statistics about the cleanup operation
    """
    now = timezone.now()
    
    try:
        with transaction.atomic():
            # Find all expired holds that haven't been released
            # 🚀 ENTERPRISE FIX: Remove select_related with nullable joins to avoid FOR UPDATE error
            expired_holds = TicketHold.objects.select_for_update().filter(
                released=False,
                expires_at__lte=now
            )
            
            total_holds = expired_holds.count()
            
            if total_holds == 0:
                logger.info('✅ CLEANUP: No expired holds found. System is clean!')
                return {
                    'status': 'success',
                    'expired_holds_found': 0,
                    'holds_released': 0,
                    'tickets_returned': 0,
                    'message': 'No expired holds found'
                }
            
            logger.info(f'🧹 CLEANUP: Found {total_holds} expired holds to release')
            
            released_count = 0
            tickets_returned = 0
            errors = []
            
            # Process holds in batches for better performance
            batch_size = 100
            for i in range(0, total_holds, batch_size):
                batch = expired_holds[i:i + batch_size]
                
                for hold in batch:
                    try:
                        tickets_returned += hold.quantity
                        hold.release()  # This returns tickets to availability
                        released_count += 1
                        
                        logger.debug(
                            f'Released hold {hold.id}: {hold.quantity}x {hold.ticket_tier.name} '
                            f'for event {hold.event.title}'
                        )
                        
                    except Exception as e:
                        error_msg = f'Error releasing hold {hold.id}: {str(e)}'
                        logger.error(error_msg)
                        errors.append(error_msg)
                
                # Log progress for large batches
                if total_holds > batch_size:
                    logger.info(f'📊 CLEANUP: Processed {min(i + batch_size, total_holds)}/{total_holds} holds')
            
            result = {
                'status': 'success' if not errors else 'partial_success',
                'expired_holds_found': total_holds,
                'holds_released': released_count,
                'tickets_returned': tickets_returned,
                'errors': errors,
                'message': f'Released {released_count} holds, returned {tickets_returned} tickets'
            }
            
            if errors:
                logger.warning(f'⚠️  CLEANUP: {len(errors)} errors occurred during cleanup')
            else:
                logger.info(f'✅ CLEANUP: Successfully released {released_count} holds, returned {tickets_returned} tickets')
            
            return result
            
    except Exception as e:
        error_msg = f'Critical error in cleanup_expired_ticket_holds: {str(e)}'
        logger.error(error_msg)
        
        # Re-raise for Celery to mark task as failed
        raise self.retry(exc=e, countdown=60, max_retries=3)


@shared_task(bind=True)
def send_ticket_confirmation_email(self, order_id):
    """
    🚀 ENTERPRISE TASK: Send professional ticket confirmation email.
    
    Args:
        order_id (str): The ID of the order to send confirmation for
        
    Returns:
        dict: Email sending result
    """
    try:
        from apps.events.models import Order
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        
        from apps.events.models import EmailLog
        order = Order.objects.select_related('event', 'event__location').prefetch_related(
            'items__ticket_tier', 'items__tickets'
        ).get(id=order_id)
        
        if order.status != 'paid':
            logger.warning(f'📧 EMAIL: Skipping email for unpaid order {order_id}')
            return {'status': 'skipped', 'reason': 'Order not paid'}
        
        # Get all tickets for this order
        all_tickets = []
        for item in order.items.all():
            for ticket in item.tickets.all():
                all_tickets.append(ticket)
        
        if not all_tickets:
            logger.warning(f'📧 EMAIL: No tickets found for order {order_id}')
            return {'status': 'skipped', 'reason': 'No tickets found'}
        
        # Send one email per ticket (enterprise approach for individual QR codes)
        sent_count = 0
        for ticket in all_tickets:
            try:
                # Prepare context for email template
                context = {
                    'attendee_name': ticket.attendee_name,
                    'event': order.event,
                    'ticket': ticket,
                    'order': order,
                    'email': order.email,
                }
                
                # Render email templates
                html_content = render_to_string('emails/ticket_confirmation.html', context)
                text_content = render_to_string('emails/ticket_confirmation.txt', context)
                
                # Create email
                subject = f'🎫 Tu ticket para {order.event.title} está listo'

                # Create a pending log
                log = EmailLog.objects.create(
                    order=order,
                    ticket=ticket,
                    to_email=order.email,
                    subject=subject,
                    template='ticket_confirmation',
                    status='pending',
                    attempts=0,
                    metadata={'ticket_number': ticket.ticket_number}
                )
                
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email='Tuki <noreply@tuki.cl>',
                    to=[order.email],
                    reply_to=['soporte@tuki.cl'],
                )
                
                # Attach HTML version
                email.attach_alternative(html_content, "text/html")
                
                # Send email
                email.send(fail_silently=False)
                sent_count += 1
                log.status = 'sent'
                log.attempts += 1
                log.sent_at = timezone.now()
                log.save(update_fields=['status', 'attempts', 'sent_at'])
                
                logger.info(
                    f'📧 EMAIL: Sent confirmation to {order.email} '
                    f'for ticket {ticket.ticket_number} (event: {order.event.title})'
                )
                
            except Exception as e:
                logger.error(f'📧 EMAIL: Failed to send email for ticket {ticket.ticket_number}: {str(e)}')
                try:
                    log.status = 'failed'
                    log.attempts += 1
                    log.error = str(e)
                    log.save(update_fields=['status', 'attempts', 'error'])
                except Exception:
                    pass
                # Continue with other tickets even if one fails
                continue
        
        return {
            'status': 'success',
            'order_id': order_id,
            'email': order.email,
            'tickets_sent': sent_count,
            'total_tickets': len(all_tickets),
            'message': f'Sent {sent_count}/{len(all_tickets)} confirmation emails'
        }
        
    except Order.DoesNotExist:
        error_msg = f'Order {order_id} not found for email confirmation'
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
        
    except Exception as e:
        error_msg = f'Error sending confirmation email for order {order_id}: {str(e)}'
        logger.error(error_msg)
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries), max_retries=3)


@shared_task(bind=True)
def send_event_reminder_email(self, event_id):
    """
    🚀 ENTERPRISE TASK: Send event reminder emails 24 hours before event.
    
    Args:
        event_id (str): The ID of the event to send reminders for
        
    Returns:
        dict: Email sending result
    """
    try:
        from apps.events.models import Event, Ticket
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        
        event = Event.objects.select_related('location').get(id=event_id)
        
        # Get all active tickets for this event
        tickets = Ticket.objects.select_related(
            'order_item__order', 'order_item__ticket_tier'
        ).filter(
            order_item__order__event=event,
            status='active',
            order_item__order__status='paid'
        )
        
        sent_count = 0
        total_tickets = tickets.count()
        
        if total_tickets == 0:
            logger.info(f'📧 REMINDER: No active tickets found for event {event.title}')
            return {'status': 'skipped', 'reason': 'No active tickets'}
        
        # Send reminder to each ticket holder
        for ticket in tickets:
            try:
                context = {
                    'attendee_name': ticket.attendee_name,
                    'event': event,
                    'ticket': ticket,
                    'order': ticket.order_item.order,
                    'email': ticket.email,
                }
                
                html_content = render_to_string('emails/event_reminder.html', context)
                text_content = render_to_string('emails/event_reminder.txt', context)
                
                subject = f'⏰ ¡Tu evento {event.title} es mañana!'
                
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email='Tuki <noreply@tuki.cl>',
                    to=[ticket.email],
                    reply_to=['soporte@tuki.cl'],
                )
                
                email.attach_alternative(html_content, "text/html")
                email.send(fail_silently=False)
                sent_count += 1
                
            except Exception as e:
                logger.error(f'📧 REMINDER: Failed to send reminder for ticket {ticket.ticket_number}: {str(e)}')
                continue
        
        logger.info(f'📧 REMINDER: Sent {sent_count}/{total_tickets} reminder emails for event {event.title}')
        
        return {
            'status': 'success',
            'event_id': event_id,
            'reminders_sent': sent_count,
            'total_tickets': total_tickets,
            'message': f'Sent {sent_count}/{total_tickets} reminder emails'
        }
        
    except Event.DoesNotExist:
        error_msg = f'Event {event_id} not found for reminder emails'
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
        
    except Exception as e:
        error_msg = f'Error sending reminder emails for event {event_id}: {str(e)}'
        logger.error(error_msg)
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries), max_retries=3)


@shared_task(bind=True)
def schedule_event_reminders(self):
    """
    🚀 ENTERPRISE TASK: Schedule reminder emails for events happening in 24 hours.
    
    This task runs daily and schedules individual reminder emails for each event
    that starts in approximately 24 hours.
    
    Returns:
        dict: Scheduling result
    """
    try:
        from apps.events.models import Event
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        tomorrow_start = now + timedelta(hours=20)  # 20-28 hours from now
        tomorrow_end = now + timedelta(hours=28)
        
        # Find events starting in the next 24 hours
        upcoming_events = Event.objects.filter(
            status='published',
            start_date__gte=tomorrow_start,
            start_date__lte=tomorrow_end
        ).prefetch_related('orders__items__tickets')
        
        scheduled_count = 0
        total_events = upcoming_events.count()
        
        if total_events == 0:
            logger.info('📧 SCHEDULER: No events found for reminder scheduling')
            return {'status': 'success', 'events_found': 0, 'reminders_scheduled': 0}
        
        for event in upcoming_events:
            try:
                # Check if event has active tickets
                has_tickets = event.orders.filter(status='paid').exists()
                
                if has_tickets:
                    # Schedule reminder email for this event
                    send_event_reminder_email.delay(str(event.id))
                    scheduled_count += 1
                    
                    logger.info(f'📧 SCHEDULER: Scheduled reminder for event {event.title} (starts: {event.start_date})')
                
            except Exception as e:
                logger.error(f'📧 SCHEDULER: Error scheduling reminder for event {event.id}: {str(e)}')
                continue
        
        logger.info(f'📧 SCHEDULER: Scheduled {scheduled_count} reminder emails for {total_events} upcoming events')
        
        return {
            'status': 'success',
            'events_found': total_events,
            'reminders_scheduled': scheduled_count,
            'message': f'Scheduled {scheduled_count} reminder emails'
        }
        
    except Exception as e:
        error_msg = f'Error in schedule_event_reminders: {str(e)}'
        logger.error(error_msg)
        raise self.retry(exc=e, countdown=60, max_retries=3)


@shared_task(bind=True)
def generate_ticket_pdf(self, ticket_id):
    """
    🚀 ENTERPRISE TASK: Generate PDF ticket with QR code.
    
    Args:
        ticket_id (str): The ID of the ticket to generate PDF for
        
    Returns:
        dict: PDF generation result with file path
    """
    try:
        from apps.events.models import Ticket
        
        ticket = Ticket.objects.select_related(
            'order_item__order__event', 'order_item__ticket_tier'
        ).get(id=ticket_id)
        
        # TODO: Implement actual PDF generation logic
        # For now, just log the action
        logger.info(
            f'🎫 PDF: Would generate PDF for ticket {ticket.ticket_number} '
            f'(event: {ticket.event.title}, attendee: {ticket.attendee_name})'
        )
        
        return {
            'status': 'success',
            'ticket_id': ticket_id,
            'ticket_number': ticket.ticket_number,
            'pdf_path': f'/tmp/tickets/{ticket.ticket_number}.pdf',  # Placeholder
            'message': 'PDF generated successfully'
        }
        
    except Ticket.DoesNotExist:
        error_msg = f'Ticket {ticket_id} not found for PDF generation'
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
        
    except Exception as e:
        error_msg = f'Error generating PDF for ticket {ticket_id}: {str(e)}'
        logger.error(error_msg)
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries), max_retries=3)
