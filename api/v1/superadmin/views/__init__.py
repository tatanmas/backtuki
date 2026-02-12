"""
SuperAdmin Views Package
Exports all view functions and viewsets for backward compatibility.
"""

from .users import SuperAdminUserViewSet
from .analytics import (
    superadmin_stats,
    sales_analytics,
    events_analytics,
    organizer_sales
)
from .organizers import (
    update_organizer_template,
    update_organizer_modules,
    update_organizer_service_fee
)
from .events import update_event_service_fee
from .flows import (
    ticket_delivery_funnel,
    ticket_delivery_issues,
    events_list,
    all_flows,
    historical_conversion_rates,
    flow_detail,
    resend_order_email,
    bulk_resend_emails
)
from .revenue import (
    revenue_migration_status,
    migrate_revenue_data
)
from .system import celery_tasks_list
from .countries import CountryViewSet
from .experiences import create_experience_from_json, update_experience_commission
from .creators_landing_slots import creators_landing_slots_list, creators_landing_slots_assign
from .creators import SuperAdminCreatorsListView

__all__ = [
    # Users
    'SuperAdminUserViewSet',
    # Analytics
    'superadmin_stats',
    'sales_analytics',
    'events_analytics',
    'organizer_sales',
    # Organizers
    'update_organizer_template',
    'update_organizer_modules',
    'update_organizer_service_fee',
    # Events
    'update_event_service_fee',
    # Flows
    'ticket_delivery_funnel',
    'ticket_delivery_issues',
    'events_list',
    'all_flows',
    'historical_conversion_rates',
    'flow_detail',
    'resend_order_email',
    'bulk_resend_emails',
    # Revenue
    'revenue_migration_status',
    'migrate_revenue_data',
    # System
    'celery_tasks_list',
    # Countries
    'CountryViewSet',
    # Experiences
    'create_experience_from_json',
    'update_experience_commission',
    'creators_landing_slots_list',
    'creators_landing_slots_assign',
    'SuperAdminCreatorsListView',
]
