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
from .events import update_event_service_fee, get_event_detail, update_ticket_tier_service_fee
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
from .finances import (
    pending_payouts,
    create_payout,
    export_payouts,
    bank_options,
)
from .system import celery_tasks_list, platform_status
from .countries import CountryViewSet
from .experiences import create_experience_from_json, update_experience_commission
from .creators_landing_slots import creators_landing_slots_list, creators_landing_slots_assign
from .creators import SuperAdminCreatorsListView
from .erasmus import (
    ErasmusLeadsView,
    ErasmusLeadsExportView,
    ErasmusLeadDetailView,
    ErasmusDashboardView,
    create_erasmus_leads_from_json,
    create_erasmus_timeline_from_json,
    create_erasmus_activity_from_json,
    ErasmusActivityListView,
    ErasmusActivityDetailView,
    ErasmusActivityInstanceListCreateView,
    ErasmusActivityInstanceDetailView,
    erasmus_activity_instances_bulk_from_json,
    ErasmusTrackingLinkViewSet,
    ErasmusExtraFieldViewSet,
    ErasmusDestinationGuideViewSet,
    ErasmusLocalPartnerViewSet,
    ErasmusWhatsAppGroupViewSet,
    erasmus_whatsapp_groups_bulk_from_json,
)
from .erasmus_slides import erasmus_slides_list, erasmus_slides_assign, erasmus_slides_create, erasmus_slides_delete
from .erasmus_registro_background import (
    erasmus_registro_background_list,
    erasmus_registro_background_create,
    erasmus_registro_background_delete,
    erasmus_registro_background_assign,
    erasmus_registro_background_reorder,
)
from .accommodations import (
    SuperAdminAccommodationListView,
    SuperAdminAccommodationDetailView,
    SuperAdminAccommodationGalleryUpdateView,
    create_accommodation_from_json,
)
from .schema import schema_for_entity
from .destinations import create_destination_from_json
from .rental_hubs import RentalHubViewSet

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
    'get_event_detail',
    'update_ticket_tier_service_fee',
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
    # Finances
    'pending_payouts',
    'create_payout',
    'export_payouts',
    'bank_options',
    # System
    'celery_tasks_list',
    'platform_status',
    # Countries
    'CountryViewSet',
    # Experiences
    'create_experience_from_json',
    'update_experience_commission',
    'creators_landing_slots_list',
    'creators_landing_slots_assign',
    'SuperAdminCreatorsListView',
    # Erasmus
    'ErasmusLeadsView',
    'ErasmusLeadsExportView',
    'ErasmusLeadDetailView',
    'ErasmusDashboardView',
    'create_erasmus_leads_from_json',
    'create_erasmus_timeline_from_json',
    'create_erasmus_activity_from_json',
    'ErasmusActivityListView',
    'ErasmusActivityDetailView',
    'ErasmusActivityInstanceListCreateView',
    'ErasmusActivityInstanceDetailView',
    'erasmus_activity_instances_bulk_from_json',
    'ErasmusTrackingLinkViewSet',
    'ErasmusExtraFieldViewSet',
    'ErasmusDestinationGuideViewSet',
    'ErasmusLocalPartnerViewSet',
    'ErasmusWhatsAppGroupViewSet',
    'erasmus_whatsapp_groups_bulk_from_json',
    'erasmus_slides_list',
    'erasmus_slides_assign',
    'erasmus_slides_create',
    'erasmus_slides_delete',
    'erasmus_registro_background_list',
    'erasmus_registro_background_create',
    'erasmus_registro_background_delete',
    'erasmus_registro_background_assign',
    'erasmus_registro_background_reorder',
    # Accommodations (photo tour)
    'SuperAdminAccommodationListView',
    'SuperAdminAccommodationDetailView',
    'SuperAdminAccommodationGalleryUpdateView',
    'create_accommodation_from_json',
    # Schema + JSON upload
    'schema_for_entity',
    'create_destination_from_json',
    'RentalHubViewSet',
]
