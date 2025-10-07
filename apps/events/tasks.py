"""
🚀 ENTERPRISE: Analytics Celery Tasks
Automated tasks for calculating and updating analytics metrics.
"""

from celery import shared_task
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Count, Sum, Avg, Q
from apps.events.models import Event
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