"""
🚀 ENTERPRISE VALIDATION ADMIN
Admin interface para el sistema de validación enterprise
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import ValidatorSession, TicketValidationLog, TicketNote, EventValidationStats


@admin.register(ValidatorSession)
class ValidatorSessionAdmin(admin.ModelAdmin):
    list_display = [
        'validator_name', 'event', 'organizer', 'start_time', 
        'duration_display', 'is_active', 'success_rate_display',
        'total_scans', 'tickets_checked_in'
    ]
    list_filter = [
        'is_active', 'organizer', 'event', 'start_time'
    ]
    search_fields = [
        'validator_name', 'event__title', 'organizer__name'
    ]
    readonly_fields = [
        'start_time', 'total_scans', 'successful_validations',
        'failed_validations', 'tickets_checked_in', 'duration_display',
        'success_rate_display'
    ]
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('validator_name', 'organizer', 'event', 'user')
        }),
        ('Sesión', {
            'fields': ('start_time', 'end_time', 'is_active', 'duration_display')
        }),
        ('Métricas', {
            'fields': (
                'total_scans', 'successful_validations', 'failed_validations',
                'tickets_checked_in', 'success_rate_display'
            )
        }),
        ('Información Técnica', {
            'fields': ('device_info', 'location'),
            'classes': ('collapse',)
        })
    )
    
    def duration_display(self, obj):
        if obj.duration:
            total_seconds = int(obj.duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        return "En curso" if obj.is_active else "N/A"
    duration_display.short_description = "Duración"
    
    def success_rate_display(self, obj):
        rate = obj.success_rate
        color = "green" if rate >= 95 else "orange" if rate >= 80 else "red"
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )
    success_rate_display.short_description = "Tasa de Éxito"


@admin.register(TicketValidationLog)
class TicketValidationLogAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'action', 'status', 'ticket_number_display',
        'validator_name', 'scan_time_display', 'message_short'
    ]
    list_filter = [
        'action', 'status', 'created_at', 
        'validator_session__event', 'validator_session__organizer'
    ]
    search_fields = [
        'ticket__ticket_number', 'validator_session__validator_name',
        'message', 'qr_data'
    ]
    readonly_fields = [
        'created_at', 'ticket', 'validator_session', 'action',
        'status', 'scan_time_ms', 'qr_data'
    ]
    
    date_hierarchy = 'created_at'
    
    def ticket_number_display(self, obj):
        if obj.ticket:
            return obj.ticket.ticket_number
        return "Sin ticket"
    ticket_number_display.short_description = "Ticket"
    
    def validator_name(self, obj):
        return obj.validator_session.validator_name
    validator_name.short_description = "Validador"
    
    def scan_time_display(self, obj):
        if obj.scan_time_ms:
            return f"{obj.scan_time_ms}ms"
        return "N/A"
    scan_time_display.short_description = "Tiempo Scan"
    
    def message_short(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_short.short_description = "Mensaje"


@admin.register(TicketNote)
class TicketNoteAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'ticket', 'note_type', 'title',
        'user', 'is_important', 'is_resolved'
    ]
    list_filter = [
        'note_type', 'is_important', 'is_resolved',
        'created_at', 'ticket__order_item__order__event'
    ]
    search_fields = [
        'ticket__ticket_number', 'title', 'content',
        'user__username', 'user__first_name', 'user__last_name'
    ]
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('ticket', 'user', 'validator_session', 'note_type')
        }),
        ('Contenido', {
            'fields': ('title', 'content')
        }),
        ('Estado', {
            'fields': ('is_important', 'is_resolved')
        }),
        ('Metadatos', {
            'fields': ('attachments', 'metadata', 'created_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(EventValidationStats)
class EventValidationStatsAdmin(admin.ModelAdmin):
    list_display = [
        'event', 'scan_rate_display', 'validation_success_rate_display',
        'checkin_rate_display', 'active_validators', 'last_updated'
    ]
    list_filter = ['event__organizer', 'last_updated']
    search_fields = ['event__title']
    readonly_fields = [
        'total_tickets', 'tickets_scanned', 'tickets_validated',
        'tickets_checked_in', 'tickets_rejected', 'first_scan_time',
        'last_scan_time', 'last_updated'
    ]
    
    def scan_rate_display(self, obj):
        rate = obj.scan_rate
        color = "green" if rate >= 80 else "orange" if rate >= 50 else "red"
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )
    scan_rate_display.short_description = "Tasa de Escaneo"
    
    def validation_success_rate_display(self, obj):
        rate = obj.validation_success_rate
        color = "green" if rate >= 95 else "orange" if rate >= 85 else "red"
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )
    validation_success_rate_display.short_description = "Tasa de Validación"
    
    def checkin_rate_display(self, obj):
        rate = obj.checkin_rate
        color = "green" if rate >= 70 else "orange" if rate >= 40 else "red"
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )
    checkin_rate_display.short_description = "Tasa de Check-in"

