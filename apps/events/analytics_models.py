"""
🚀 ENTERPRISE: Event Analytics and Tracking Models
Advanced analytics models for tracking user behavior, conversions, and performance metrics.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from core.models import BaseModel
import uuid

User = get_user_model()


class EventView(BaseModel):
    """
    🚀 ENTERPRISE: Track event page views for analytics and conversion tracking.
    """
    
    VIEW_SOURCE_CHOICES = (
        ('web', _('Website')),
        ('mobile_app', _('Mobile App')),
        ('social_media', _('Social Media')),
        ('direct', _('Direct Link')),
        ('search', _('Search Engine')),
        ('email', _('Email Campaign')),
        ('partner', _('Partner Site')),
        ('qr_code', _('QR Code')),
        ('other', _('Other')),
    )
    
    DEVICE_TYPE_CHOICES = (
        ('mobile', _('Mobile')),
        ('tablet', _('Tablet')),
        ('desktop', _('Desktop')),
        ('unknown', _('Unknown')),
    )
    
    # Core tracking fields
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='views',
        verbose_name=_("event")
    )
    
    # User tracking (optional - for logged-in users)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='event_views',
        verbose_name=_("user"),
        null=True,
        blank=True
    )
    
    # Session tracking
    session_id = models.CharField(
        _("session ID"),
        max_length=40,
        help_text=_("Anonymous session identifier")
    )
    
    # Request metadata
    ip_address = models.GenericIPAddressField(_("IP address"))
    user_agent = models.TextField(_("user agent"), blank=True)
    referer = models.URLField(_("referer"), blank=True, null=True)
    
    # UTM and campaign tracking
    utm_source = models.CharField(_("UTM source"), max_length=100, blank=True)
    utm_medium = models.CharField(_("UTM medium"), max_length=100, blank=True)
    utm_campaign = models.CharField(_("UTM campaign"), max_length=100, blank=True)
    utm_term = models.CharField(_("UTM term"), max_length=100, blank=True)
    utm_content = models.CharField(_("UTM content"), max_length=100, blank=True)
    
    # Derived analytics fields
    view_source = models.CharField(
        _("view source"),
        max_length=20,
        choices=VIEW_SOURCE_CHOICES,
        default='web'
    )
    device_type = models.CharField(
        _("device type"),
        max_length=20,
        choices=DEVICE_TYPE_CHOICES,
        default='unknown'
    )
    
    # Geographic data (optional)
    country = models.CharField(_("country"), max_length=2, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    
    # Engagement metrics
    time_on_page = models.PositiveIntegerField(
        _("time on page (seconds)"),
        null=True,
        blank=True,
        help_text=_("Time spent viewing the event page")
    )
    
    # Conversion tracking
    converted_to_purchase = models.BooleanField(
        _("converted to purchase"),
        default=False,
        help_text=_("Whether this view led to a ticket purchase")
    )
    conversion_order = models.ForeignKey(
        'events.Order',
        on_delete=models.SET_NULL,
        related_name='source_views',
        verbose_name=_("conversion order"),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _("event view")
        verbose_name_plural = _("event views")
        indexes = [
            models.Index(fields=['event', 'created_at']),
            models.Index(fields=['session_id', 'created_at']),
            models.Index(fields=['ip_address', 'created_at']),
            models.Index(fields=['view_source', 'device_type']),
            models.Index(fields=['converted_to_purchase']),
        ]
    
    def __str__(self):
        return f"View: {self.event.title} at {self.created_at}"
    
    @classmethod
    def track_view(cls, event, request, session_id=None):
        """
        🚀 ENTERPRISE: Track an event view with full analytics data.
        """
        from django.contrib.gis.geoip2 import GeoIP2
        from user_agents import parse
        
        # Get or create session ID
        if not session_id:
            session_id = request.session.session_key or str(uuid.uuid4())
        
        # Parse user agent
        ua = parse(request.META.get('HTTP_USER_AGENT', ''))
        device_type = 'mobile' if ua.is_mobile else 'tablet' if ua.is_tablet else 'desktop'
        
        # Determine view source from referer
        referer = request.META.get('HTTP_REFERER', '')
        view_source = cls._determine_view_source(referer, request.GET)
        
        # Geographic data (optional - requires GeoIP2)
        country = ''
        city = ''
        try:
            g = GeoIP2()
            ip = cls._get_client_ip(request)
            geo_data = g.city(ip)
            country = geo_data.get('country_code', '')
            city = geo_data.get('city', '')
        except:
            pass
        
        # Create view record
        view = cls.objects.create(
            event=event,
            user=request.user if request.user.is_authenticated else None,
            session_id=session_id,
            ip_address=cls._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            referer=referer,
            utm_source=request.GET.get('utm_source', ''),
            utm_medium=request.GET.get('utm_medium', ''),
            utm_campaign=request.GET.get('utm_campaign', ''),
            utm_term=request.GET.get('utm_term', ''),
            utm_content=request.GET.get('utm_content', ''),
            view_source=view_source,
            device_type=device_type,
            country=country,
            city=city
        )
        
        return view
    
    @staticmethod
    def _get_client_ip(request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def _determine_view_source(referer, get_params):
        """Determine view source from referer and UTM parameters."""
        if get_params.get('utm_source'):
            utm_source = get_params.get('utm_source', '').lower()
            if 'facebook' in utm_source or 'instagram' in utm_source or 'twitter' in utm_source:
                return 'social_media'
            elif 'email' in utm_source or 'newsletter' in utm_source:
                return 'email'
            elif 'partner' in utm_source:
                return 'partner'
            elif 'qr' in utm_source:
                return 'qr_code'
        
        if referer:
            referer_lower = referer.lower()
            if any(social in referer_lower for social in ['facebook', 'instagram', 'twitter', 'linkedin', 'tiktok']):
                return 'social_media'
            elif any(search in referer_lower for search in ['google', 'bing', 'yahoo', 'duckduckgo']):
                return 'search'
            elif 'mail' in referer_lower or 'campaign' in referer_lower:
                return 'email'
            else:
                return 'web'
        
        return 'direct'


class ConversionFunnel(BaseModel):
    """
    🚀 ENTERPRISE: Track conversion funnel stages for events.
    """
    
    FUNNEL_STAGE_CHOICES = (
        ('view', _('Event View')),
        ('ticket_selection', _('Ticket Selection')),
        ('checkout_start', _('Checkout Started')),
        ('payment_info', _('Payment Info Entered')),
        ('purchase_complete', _('Purchase Completed')),
        ('abandoned', _('Abandoned')),
    )
    
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='funnel_stages',
        verbose_name=_("event")
    )
    
    session_id = models.CharField(_("session ID"), max_length=40)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("user")
    )
    
    stage = models.CharField(
        _("funnel stage"),
        max_length=20,
        choices=FUNNEL_STAGE_CHOICES
    )
    
    # Stage-specific data
    ticket_tier = models.ForeignKey(
        'events.TicketTier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("ticket tier")
    )
    quantity = models.PositiveIntegerField(_("quantity"), null=True, blank=True)
    
    # Timing data
    time_from_view = models.PositiveIntegerField(
        _("time from initial view (seconds)"),
        null=True,
        blank=True
    )
    
    # Completion data
    order = models.ForeignKey(
        'events.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("completed order")
    )
    
    class Meta:
        verbose_name = _("conversion funnel stage")
        verbose_name_plural = _("conversion funnel stages")
        indexes = [
            models.Index(fields=['event', 'stage', 'created_at']),
            models.Index(fields=['session_id', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.event.title} - {self.get_stage_display()}"


class EventPerformanceMetrics(BaseModel):
    """
    🚀 ENTERPRISE: Aggregated performance metrics for events (computed daily).
    """
    
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='performance_metrics',
        verbose_name=_("event")
    )
    
    date = models.DateField(_("date"))
    
    # View metrics
    total_views = models.PositiveIntegerField(_("total views"), default=0)
    unique_views = models.PositiveIntegerField(_("unique views"), default=0)
    avg_time_on_page = models.FloatField(_("average time on page"), default=0)
    
    # Conversion metrics
    total_conversions = models.PositiveIntegerField(_("total conversions"), default=0)
    conversion_rate = models.FloatField(_("conversion rate"), default=0)
    
    # Revenue metrics (effective revenue)
    total_revenue = models.DecimalField(
        _("total revenue"),
        max_digits=12,
        decimal_places=2,
        default=0
    )
    avg_order_value = models.DecimalField(
        _("average order value"),
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    # Traffic source breakdown
    web_views = models.PositiveIntegerField(_("web views"), default=0)
    mobile_views = models.PositiveIntegerField(_("mobile views"), default=0)
    social_media_views = models.PositiveIntegerField(_("social media views"), default=0)
    direct_views = models.PositiveIntegerField(_("direct views"), default=0)
    
    class Meta:
        verbose_name = _("event performance metrics")
        verbose_name_plural = _("event performance metrics")
        unique_together = ['event', 'date']
        indexes = [
            models.Index(fields=['event', 'date']),
            models.Index(fields=['date']),
        ]
    
    def __str__(self):
        return f"{self.event.title} - {self.date}"
    
    @classmethod
    def calculate_daily_metrics(cls, event, date):
        """
        🚀 ENTERPRISE: Calculate and store daily metrics for an event.
        """
        from django.db.models import Count, Avg, Sum
        
        # Get views for the date
        views = EventView.objects.filter(
            event=event,
            created_at__date=date
        )
        
        # Get conversions for the date
        conversions = views.filter(converted_to_purchase=True)
        
        # Get orders for the date
        orders = event.orders.filter(
            status='paid',
            created_at__date=date
        )
        
        # Calculate metrics
        total_views = views.count()
        unique_views = views.values('session_id').distinct().count()
        avg_time = views.aggregate(avg=Avg('time_on_page'))['avg'] or 0
        
        total_conversions = conversions.count()
        conversion_rate = (total_conversions / total_views * 100) if total_views > 0 else 0
        
        revenue_data = orders.aggregate(
            total=Sum('total'),
            avg=Avg('total')
        )
        total_revenue = revenue_data['total'] or 0
        avg_order_value = revenue_data['avg'] or 0
        
        # Traffic source breakdown
        source_breakdown = views.values('view_source').annotate(count=Count('id'))
        web_views = next((item['count'] for item in source_breakdown if item['view_source'] == 'web'), 0)
        mobile_views = views.filter(device_type='mobile').count()
        social_media_views = next((item['count'] for item in source_breakdown if item['view_source'] == 'social_media'), 0)
        direct_views = next((item['count'] for item in source_breakdown if item['view_source'] == 'direct'), 0)
        
        # Create or update metrics
        metrics, created = cls.objects.update_or_create(
            event=event,
            date=date,
            defaults={
                'total_views': total_views,
                'unique_views': unique_views,
                'avg_time_on_page': avg_time,
                'total_conversions': total_conversions,
                'conversion_rate': conversion_rate,
                'total_revenue': total_revenue,
                'avg_order_value': avg_order_value,
                'web_views': web_views,
                'mobile_views': mobile_views,
                'social_media_views': social_media_views,
                'direct_views': direct_views,
            }
        )
        
        return metrics
