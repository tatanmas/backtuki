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
    update_organizer_modules,
    update_organizer_service_fee,
    update_event_service_fee,
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
    # 🚀 ENTERPRISE: JSON Experience Creation
    create_experience_from_json,
    update_experience_commission,
    creators_landing_slots_list,
    creators_landing_slots_assign,
)
from .whatsapp_views import (
    whatsapp_status,
    whatsapp_disconnect,
    whatsapp_qr,
    whatsapp_profile_picture,
    whatsapp_reservations,
    whatsapp_operators,
    whatsapp_bind_experience_operator,
    whatsapp_messages,
    whatsapp_mark_message_reservation,
    whatsapp_chats,
    whatsapp_chat_info,
    whatsapp_update_chat,
    whatsapp_mark_chat_read,
    whatsapp_assign_chat_operator,
    whatsapp_sync_chats,
    whatsapp_send_message,
    whatsapp_groups,
    whatsapp_group_info,
    whatsapp_assign_group_operator,
    whatsapp_experiences,
    whatsapp_experience_group,
    whatsapp_operator_detail,
    whatsapp_operator_default_group,
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
    path('organizers/<str:organizer_id>/modules/', update_organizer_modules, name='update-organizer-modules'),
    path('organizers/<str:organizer_id>/service-fee/', update_organizer_service_fee, name='update-organizer-service-fee'),
    path('events/<str:event_id>/service-fee/', update_event_service_fee, name='update-event-service-fee'),
    
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
    
    # 🚀 ENTERPRISE: WhatsApp Integration Endpoints
    path('whatsapp/status/', whatsapp_status, name='whatsapp-status'),
    path('whatsapp/disconnect/', whatsapp_disconnect, name='whatsapp-disconnect'),
    path('whatsapp/qr/', whatsapp_qr, name='whatsapp-qr'),
    path('whatsapp/reservations/', whatsapp_reservations, name='whatsapp-reservations'),
    path('whatsapp/operators/', whatsapp_operators, name='whatsapp-operators'),
    path('whatsapp/bind-experience-operator/', whatsapp_bind_experience_operator, name='whatsapp-bind-experience-operator'),
    path('whatsapp/messages/', whatsapp_messages, name='whatsapp-messages'),
    path('whatsapp/messages/<str:message_id>/mark-reservation/', whatsapp_mark_message_reservation, name='whatsapp-mark-message-reservation'),
    path('whatsapp/chats/', whatsapp_chats, name='whatsapp-chats'),
    path('whatsapp/profile-picture/<str:chat_id>/', whatsapp_profile_picture, name='whatsapp-profile-picture'),
    path('whatsapp/chats/sync/', whatsapp_sync_chats, name='whatsapp-sync-chats'),
    path('whatsapp/chats/<str:chat_id>/', whatsapp_chat_info, name='whatsapp-chat-info'),
    path('whatsapp/chats/<str:chat_id>/update/', whatsapp_update_chat, name='whatsapp-update-chat'),
    path('whatsapp/chats/<str:chat_id>/mark-read/', whatsapp_mark_chat_read, name='whatsapp-mark-chat-read'),
    path('whatsapp/chats/<str:chat_id>/assign-operator/', whatsapp_assign_chat_operator, name='whatsapp-assign-chat-operator'),
    path('whatsapp/send-message/', whatsapp_send_message, name='whatsapp-send-message'),
    path('whatsapp/groups/', whatsapp_groups, name='whatsapp-groups'),
    path('whatsapp/groups/<str:group_id>/info/', whatsapp_group_info, name='whatsapp-group-info'),
    path('whatsapp/groups/<str:group_id>/assign-operator/', whatsapp_assign_group_operator, name='whatsapp-assign-group-operator'),
    path('whatsapp/experiences/', whatsapp_experiences, name='whatsapp-experiences'),
    path('whatsapp/experiences/<str:experience_id>/group/', whatsapp_experience_group, name='whatsapp-experience-group'),
    path('whatsapp/operators/<str:operator_id>/', whatsapp_operator_detail, name='whatsapp-operator-detail'),
    path('whatsapp/operators/<str:operator_id>/default-group/', whatsapp_operator_default_group, name='whatsapp-operator-default-group'),
    
    # 🚀 ENTERPRISE: JSON Experience Creation
    path('experiences/create-from-json/', create_experience_from_json, name='create-experience-from-json'),
    path('experiences/<uuid:experience_id>/commission/', update_experience_commission, name='update-experience-commission'),
    path('creators-landing-slots/', creators_landing_slots_list, name='creators-landing-slots-list'),
    path('creators-landing-slots/assign/', creators_landing_slots_assign, name='creators-landing-slots-assign'),
]

