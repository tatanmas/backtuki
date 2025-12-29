"""URL Configuration for Super Admin API."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SuperAdminUserViewSet, 
    CountryViewSet,
    superadmin_stats, 
    sales_analytics, 
    organizer_sales, 
    events_analytics, 
    update_organizer_template,
    # 🚀 ENTERPRISE: Platform Flow Monitoring
    ticket_delivery_funnel,
    ticket_delivery_issues,
    all_flows,
    flow_detail,
    resend_order_email,
    bulk_resend_emails,
    celery_tasks_list,
    historical_conversion_rates,
    events_list,
    # 🚀 ENTERPRISE: Revenue Migration
    revenue_migration_status,
    migrate_revenue_data,
)

# Create router
router = DefaultRouter()
router.register(r'users', SuperAdminUserViewSet, basename='superadmin-users')
router.register(r'countries', CountryViewSet, basename='country')

urlpatterns = [
    path('', include(router.urls)),
    path('stats/', superadmin_stats, name='superadmin-stats'),
    path('sales-analytics/', sales_analytics, name='sales-analytics'),
    path('organizer-sales/', organizer_sales, name='organizer-sales'),
    path('events-analytics/', events_analytics, name='events-analytics'),
    path('organizers/<str:organizer_id>/template/', update_organizer_template, name='update-organizer-template'),
    
    # 🚀 ENTERPRISE: Platform Flow Monitoring Endpoints
    path('ticket-delivery-funnel/', ticket_delivery_funnel, name='ticket-delivery-funnel'),
    path('ticket-delivery-issues/', ticket_delivery_issues, name='ticket-delivery-issues'),
    path('events-list/', events_list, name='events-list'),
    path('flows/', all_flows, name='all-flows'),
    # IMPORTANT: Specific paths must come before generic ones
    path('flows/bulk-resend-emails/', bulk_resend_emails, name='bulk-resend-emails'),
    path('flows/<str:flow_id>/resend-email/', resend_order_email, name='resend-order-email'),
    path('flows/<str:flow_id>/', flow_detail, name='flow-detail'),
    path('celery-tasks/', celery_tasks_list, name='celery-tasks-list'),
    path('historical-conversion-rates/', historical_conversion_rates, name='historical-conversion-rates'),
    
    # 🚀 ENTERPRISE: Revenue Migration Endpoints
    path('revenue-migration/status/', revenue_migration_status, name='revenue-migration-status'),
    path('revenue-migration/migrate/', migrate_revenue_data, name='migrate-revenue-data'),
]

