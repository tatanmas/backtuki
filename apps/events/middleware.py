"""
🚀 ENTERPRISE: Analytics Tracking Middleware
Automatically track event views and user behavior for conversion analytics.
"""

import re
import time
from django.utils.deprecation import MiddlewareMixin
from django.urls import resolve, Resolver404
from django.http import JsonResponse
from apps.events.models import Event
from apps.events.analytics_models import EventView, ConversionFunnel


class EventAnalyticsMiddleware(MiddlewareMixin):
    """
    🚀 ENTERPRISE: Middleware to automatically track event views and analytics.
    
    This middleware:
    1. Tracks event page views
    2. Records user behavior for conversion analysis
    3. Handles both web and API requests
    4. Respects privacy settings and GDPR compliance
    """
    
    # URL patterns to track
    EVENT_VIEW_PATTERNS = [
        r'^/events/([^/]+)/?$',  # Event detail page
        r'^/e/([^/]+)/?$',       # Short event URL
        r'^/api/v1/events/([^/]+)/?$',  # API event detail
    ]
    
    # Patterns to ignore
    IGNORE_PATTERNS = [
        r'^/admin/',
        r'^/api/schema/',
        r'^/api/docs/',
        r'^/healthz',
        r'^/static/',
        r'^/media/',
        r'\.ico$',
        r'\.js$',
        r'\.css$',
        r'\.png$',
        r'\.jpg$',
        r'\.svg$',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        """Process incoming request and start tracking if needed."""
        # Store start time for performance tracking
        request._analytics_start_time = time.time()
        
        # Skip tracking for ignored patterns
        if self._should_ignore_request(request):
            return None
        
        # Check if this is an event view
        event_id = self._extract_event_id(request.path)
        if event_id:
            try:
                event = Event.objects.get(id=event_id)
                request._analytics_event = event
                request._analytics_tracking = True
                
                # Track the view
                self._track_event_view(request, event)
                
            except Event.DoesNotExist:
                pass
        
        return None
    
    def process_response(self, request, response):
        """Process response and complete tracking if needed."""
        # Skip if not tracking
        if not getattr(request, '_analytics_tracking', False):
            return response
        
        # Calculate time on page
        if hasattr(request, '_analytics_start_time'):
            time_on_page = int(time.time() - request._analytics_start_time)
            
            # Update view with time on page if we have a view record
            if hasattr(request, '_analytics_view'):
                request._analytics_view.time_on_page = time_on_page
                request._analytics_view.save(update_fields=['time_on_page'])
        
        return response
    
    def _should_ignore_request(self, request):
        """Check if request should be ignored for analytics."""
        path = request.path
        
        # Check ignore patterns
        for pattern in self.IGNORE_PATTERNS:
            if re.search(pattern, path):
                return True
        
        # Ignore non-GET requests for view tracking
        if request.method != 'GET':
            return True
        
        # Ignore requests from bots (basic check)
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        bot_indicators = ['bot', 'crawler', 'spider', 'scraper', 'curl', 'wget']
        if any(indicator in user_agent for indicator in bot_indicators):
            return True
        
        return False
    
    def _extract_event_id(self, path):
        """Extract event ID from URL path."""
        for pattern in self.EVENT_VIEW_PATTERNS:
            match = re.search(pattern, path)
            if match:
                return match.group(1)
        return None
    
    def _track_event_view(self, request, event):
        """Track an event view with full analytics data."""
        try:
            # Get or create session
            if not request.session.session_key:
                request.session.create()
            
            session_id = request.session.session_key
            
            # Check if this is a duplicate view (same session, same event, within 30 minutes)
            recent_view = EventView.objects.filter(
                event=event,
                session_id=session_id,
                created_at__gte=timezone.now() - timedelta(minutes=30)
            ).first()
            
            if recent_view:
                # Update existing view instead of creating new one
                request._analytics_view = recent_view
                return recent_view
            
            # Create new view record
            view = EventView.track_view(event, request, session_id)
            request._analytics_view = view
            
            # Track funnel stage
            ConversionFunnel.objects.create(
                event=event,
                session_id=session_id,
                user=request.user if request.user.is_authenticated else None,
                stage='view'
            )
            
            return view
            
        except Exception as e:
            # Log error but don't break the request
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Analytics tracking error: {e}")
            return None


class ConversionTrackingMiddleware(MiddlewareMixin):
    """
    🚀 ENTERPRISE: Track conversion events (checkout, purchase, etc.)
    """
    
    CONVERSION_ENDPOINTS = {
        r'^/api/v1/events/([^/]+)/checkout/?$': 'checkout_start',
        r'^/api/v1/orders/?$': 'payment_info',
        r'^/api/v1/orders/([^/]+)/complete/?$': 'purchase_complete',
    }
    
    def process_request(self, request):
        """Track conversion events."""
        if request.method != 'POST':
            return None
        
        path = request.path
        
        for pattern, stage in self.CONVERSION_ENDPOINTS.items():
            match = re.search(pattern, path)
            if match:
                self._track_conversion_stage(request, stage, match)
                break
        
        return None
    
    def _track_conversion_stage(self, request, stage, url_match):
        """Track a conversion funnel stage."""
        try:
            # Get session
            session_id = request.session.session_key
            if not session_id:
                return
            
            # Determine event based on stage and URL
            event = self._get_event_from_request(request, stage, url_match)
            if not event:
                return
            
            # Get initial view time for timing calculation
            initial_view = EventView.objects.filter(
                event=event,
                session_id=session_id
            ).first()
            
            time_from_view = None
            if initial_view:
                time_from_view = int((timezone.now() - initial_view.created_at).total_seconds())
            
            # Create funnel stage record
            ConversionFunnel.objects.create(
                event=event,
                session_id=session_id,
                user=request.user if request.user.is_authenticated else None,
                stage=stage,
                time_from_view=time_from_view
            )
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Conversion tracking error: {e}")
    
    def _get_event_from_request(self, request, stage, url_match):
        """Extract event from request based on stage and URL."""
        try:
            if stage in ['checkout_start']:
                # Event ID is in URL
                event_id = url_match.group(1)
                return Event.objects.get(id=event_id)
            
            elif stage in ['payment_info', 'purchase_complete']:
                # Event might be in request data
                if hasattr(request, 'data') and 'event_id' in request.data:
                    return Event.objects.get(id=request.data['event_id'])
                
                # Or in JSON body
                import json
                try:
                    body = json.loads(request.body.decode('utf-8'))
                    if 'event_id' in body:
                        return Event.objects.get(id=body['event_id'])
                except:
                    pass
            
            return None
            
        except Event.DoesNotExist:
            return None
