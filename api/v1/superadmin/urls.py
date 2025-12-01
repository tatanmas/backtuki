"""URL Configuration for Super Admin API."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SuperAdminUserViewSet, 
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
    celery_tasks_list
)

# Create router
router = DefaultRouter()
router.register(r'users', SuperAdminUserViewSet, basename='superadmin-users')

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
    path('flows/', all_flows, name='all-flows'),
    path('flows/<str:flow_id>/', flow_detail, name='flow-detail'),
    path('celery-tasks/', celery_tasks_list, name='celery-tasks-list'),
]

