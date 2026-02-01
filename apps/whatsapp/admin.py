"""Django admin for WhatsApp app."""
from django.contrib import admin
from .models import (
    WhatsAppSession,
    WhatsAppMessage,
    WhatsAppReservationRequest,
    TourOperator,
    ExperienceOperatorBinding
)


@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    list_display = ['status', 'phone_number', 'name', 'last_seen', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['phone_number', 'name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ['whatsapp_id', 'phone', 'type', 'processed', 'timestamp']
    list_filter = ['type', 'processed', 'timestamp']
    search_fields = ['whatsapp_id', 'phone', 'content']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(WhatsAppReservationRequest)
class WhatsAppReservationRequestAdmin(admin.ModelAdmin):
    list_display = ['tour_code', 'operator', 'status', 'passengers', 'timeout_at', 'created_at']
    list_filter = ['status', 'created_at', 'timeout_at']
    search_fields = ['tour_code', 'operator__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['whatsapp_message', 'operator', 'experience']


@admin.register(TourOperator)
class TourOperatorAdmin(admin.ModelAdmin):
    list_display = ['name', 'whatsapp_number', 'contact_phone', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'whatsapp_number', 'contact_phone']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ExperienceOperatorBinding)
class ExperienceOperatorBindingAdmin(admin.ModelAdmin):
    list_display = ['experience', 'tour_operator', 'priority', 'is_active']
    list_filter = ['is_active', 'priority']
    search_fields = ['experience__title', 'tour_operator__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['experience', 'tour_operator']

