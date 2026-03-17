"""
SuperAdmin Views Package
Exports all view functions and viewsets for backward compatibility.
"""

from .users import SuperAdminUserViewSet
from .analytics import (
    superadmin_stats,
    sales_analytics,
    events_analytics,
    organizer_sales,
    dashboard_time_series,
)
from .organizers import (
    update_organizer_template,
    update_organizer_modules,
    update_organizer_service_fee,
    impersonate_organizer,
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
from .finance_center import (
    finance_sync,
    finance_overview,
    finance_payees,
    finance_payee_detail,
    finance_payouts,
    finance_create_paid_payout,
    finance_update_payout,
    finance_batches,
    finance_batch_export,
    finance_batch_mark_paid,
    finance_export_files,
    finance_platform_settings,
    finance_payout_attachment_upload,
    finance_audit,
)
from .orders import (
    orders_list,
    order_detail,
    order_exclude_from_revenue,
    order_soft_delete,
    order_restore,
    order_permanent_delete,
)
from .system import (
    celery_tasks_list,
    platform_status,
    platform_uptime_report,
    deploys_list,
    email_health_check,
)
from .countries import CountryViewSet
from .experiences import (
    create_experience_from_json,
    update_experience_commission,
    superadmin_experience_detail,
    experience_landing_destinations,
    superadmin_experience_instances,
    superadmin_experience_instances_block_by_date,
    superadmin_experience_instances_unblock_by_date,
    superadmin_experience_regenerate_instances,
    superadmin_experience_instance_bookings,
    superadmin_experience_instance_cancel_and_notify,
    superadmin_experience_bookings_by_date,
)
from .creators_landing_slots import creators_landing_slots_list, creators_landing_slots_assign
from .creators import SuperAdminCreatorsListView
from .erasmus import (
    ErasmusLeadsView,
    ErasmusLeadsExportView,
    ErasmusLeadDetailView,
    ErasmusLeadWelcomeMessageView,
    ErasmusWelcomeMessageTemplatesView,
    ErasmusDashboardView,
    create_erasmus_leads_from_json,
    create_erasmus_timeline_from_json,
    create_erasmus_activity_from_json,
    link_experience_to_erasmus_activity,
    ErasmusActivityListView,
    ErasmusActivityDetailView,
    ErasmusActivityInstanceListCreateView,
    ErasmusActivityInstanceDetailView,
    ErasmusActivityInstanceInscriptionsView,
    ErasmusActivityPublicLinkView,
    ErasmusActivityReviewsListView,
    ErasmusActivityReviewDeleteView,
    erasmus_activity_instances_bulk_from_json,
    ErasmusTrackingLinkViewSet,
    ErasmusExtraFieldViewSet,
    ErasmusActivityExtraFieldViewSet,
    ErasmusDestinationGuideViewSet,
    ErasmusLocalPartnerViewSet,
    ErasmusWhatsAppGroupViewSet,
    erasmus_whatsapp_groups_bulk_from_json,
    erasmus_whatsapp_group_fetch_image,
    ErasmusRumiNotificationConfigView,
    erasmus_inscription_payment_exclude_from_revenue,
)
from .erasmus_slides import erasmus_slides_list, erasmus_slides_assign, erasmus_slides_create, erasmus_slides_delete, erasmus_slides_reorder
from .hero_vitrina import hero_vitrina_list, hero_vitrina_add, hero_vitrina_remove, hero_vitrina_reorder
from .erasmus_registro_background import (
    erasmus_registro_background_list,
    erasmus_registro_background_create,
    erasmus_registro_background_delete,
    erasmus_registro_background_assign,
    erasmus_registro_background_reorder,
)
from .auth_background import (
    auth_background_list,
    auth_background_create,
    auth_background_delete,
    auth_background_assign,
    auth_background_reorder,
)
from .accommodations import (
    SuperAdminAccommodationListView,
    SuperAdminAccommodationDetailView,
    SuperAdminAccommodationGalleryUpdateView,
    create_accommodation_from_json,
    update_accommodation_from_json,
    bulk_upload_gallery_zip,
    accommodation_blocked_dates,
)
from .car_rental import (
    SuperAdminCarRentalCompanyListView,
    SuperAdminCarRentalCompanyDetailView,
    SuperAdminCarListView,
    SuperAdminCarDetailView,
    SuperAdminCarGalleryUpdateView,
    create_car_rental_company_from_json,
    create_car_from_json,
)
from .schema import schema_for_entity
from .destinations import create_destination_from_json
from .rental_hubs import RentalHubViewSet
from .travel_guides import (
    TravelGuideListView,
    TravelGuideDetailView,
    TravelGuideCreateView,
    create_travel_guide_from_json,
    TravelGuideCreateHiddenInstanceView,
    TravelGuideDeleteHiddenInstanceView,
)
from .contests import (
    ContestListView,
    ContestDetailView,
    ContestCreateView,
    ContestSlidesView,
    ContestSlideAssignView,
    ContestSlideDeleteView,
    ContestSlidesReorderView,
    ContestExtraFieldViewSet,
    ContestParticipantsView,
    ContestParticipantsExportView,
)

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
    'impersonate_organizer',
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
    'finance_sync',
    'finance_overview',
    'finance_payees',
    'finance_payee_detail',
    'finance_payouts',
    'finance_create_paid_payout',
    'finance_update_payout',
    'finance_batches',
    'finance_batch_export',
    'finance_batch_mark_paid',
    'finance_export_files',
    'finance_platform_settings',
    'finance_payout_attachment_upload',
    'finance_audit',
    # System
    'celery_tasks_list',
    'platform_status',
    'platform_uptime_report',
    'deploys_list',
    # Countries
    'CountryViewSet',
    # Experiences
    'create_experience_from_json',
    'update_experience_commission',
    'superadmin_experience_detail',
    'experience_landing_destinations',
    'superadmin_experience_instances',
    'superadmin_experience_instances_block_by_date',
    'superadmin_experience_instances_unblock_by_date',
    'superadmin_experience_regenerate_instances',
    'superadmin_experience_instance_bookings',
    'superadmin_experience_instance_cancel_and_notify',
    'superadmin_experience_bookings_by_date',
    'creators_landing_slots_list',
    'creators_landing_slots_assign',
    'SuperAdminCreatorsListView',
    # Erasmus
    'ErasmusLeadsView',
    'ErasmusLeadsExportView',
    'ErasmusLeadDetailView',
    'ErasmusLeadWelcomeMessageView',
    'ErasmusWelcomeMessageTemplatesView',
    'ErasmusDashboardView',
    'create_erasmus_leads_from_json',
    'create_erasmus_timeline_from_json',
    'create_erasmus_activity_from_json',
    'link_experience_to_erasmus_activity',
    'ErasmusActivityListView',
    'ErasmusActivityDetailView',
    'ErasmusActivityInstanceListCreateView',
    'ErasmusActivityInstanceDetailView',
    'ErasmusActivityInstanceInscriptionsView',
    'erasmus_activity_instances_bulk_from_json',
    'ErasmusTrackingLinkViewSet',
    'ErasmusExtraFieldViewSet',
    'ErasmusActivityExtraFieldViewSet',
    'ErasmusDestinationGuideViewSet',
    'ErasmusLocalPartnerViewSet',
    'ErasmusWhatsAppGroupViewSet',
    'erasmus_whatsapp_groups_bulk_from_json',
    'erasmus_whatsapp_group_fetch_image',
    'ErasmusRumiNotificationConfigView',
    'erasmus_slides_list',
    'erasmus_slides_assign',
    'erasmus_slides_create',
    'erasmus_slides_delete',
    'erasmus_slides_reorder',
    'hero_vitrina_list',
    'hero_vitrina_add',
    'hero_vitrina_remove',
    'hero_vitrina_reorder',
    'erasmus_registro_background_list',
    'erasmus_registro_background_create',
    'erasmus_registro_background_delete',
    'erasmus_registro_background_assign',
    'erasmus_registro_background_reorder',
    'auth_background_list',
    'auth_background_create',
    'auth_background_delete',
    'auth_background_assign',
    'auth_background_reorder',
    # Accommodations (photo tour)
    'SuperAdminAccommodationListView',
    'SuperAdminAccommodationDetailView',
    'SuperAdminAccommodationGalleryUpdateView',
    'create_accommodation_from_json',
    'update_accommodation_from_json',
    'bulk_upload_gallery_zip',
    'accommodation_blocked_dates',
    # Car rental
    'SuperAdminCarRentalCompanyListView',
    'SuperAdminCarRentalCompanyDetailView',
    'SuperAdminCarListView',
    'SuperAdminCarDetailView',
    'SuperAdminCarGalleryUpdateView',
    'create_car_rental_company_from_json',
    'create_car_from_json',
    # Schema + JSON upload
    'schema_for_entity',
    'create_destination_from_json',
    'RentalHubViewSet',
    # Travel guides
    'TravelGuideListView',
    'TravelGuideDetailView',
    'TravelGuideCreateView',
    'create_travel_guide_from_json',
    'TravelGuideCreateHiddenInstanceView',
    'TravelGuideDeleteHiddenInstanceView',
    # Contests / Sorteos
    'ContestListView',
    'ContestDetailView',
    'ContestCreateView',
    'ContestSlidesView',
    'ContestSlideAssignView',
    'ContestSlideDeleteView',
    'ContestSlidesReorderView',
    'ContestExtraFieldViewSet',
    'ContestParticipantsView',
    'ContestParticipantsExportView',
]
