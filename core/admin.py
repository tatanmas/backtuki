"""
🚀 ENTERPRISE: Admin configuration for Platform Flow Monitoring.

This module provides comprehensive admin interfaces for monitoring and debugging
platform flows, Celery tasks, and flow events.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from core.models import PlatformFlow, PlatformFlowEvent, CeleryTaskLog


@admin.register(PlatformFlow)
class PlatformFlowAdmin(admin.ModelAdmin):
    """Admin interface for PlatformFlow model."""
    
    list_display = [
        'id_short',
        'flow_type',
        'status_badge',
        'user_link',
        'organizer_link',
        'order_link',
        'created_at',
        'duration',
        'events_count',
    ]
    
    list_filter = [
        'flow_type',
        'status',
        'created_at',
        'completed_at',
    ]
    
    search_fields = [
        'id',
        'user__email',
        'organizer__business_name',
        'primary_order__order_number',
    ]
    
    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'completed_at',
        'failed_at',
        'events_timeline',
    ]
    
    fieldsets = (
        ('Flow Information', {
            'fields': ('id', 'flow_type', 'status', 'created_at', 'updated_at')
        }),
        ('Business Context', {
            'fields': ('user', 'organizer', 'primary_order', 'event', 'experience')
        }),
        ('Timing', {
            'fields': ('completed_at', 'failed_at')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Events Timeline', {
            'fields': ('events_timeline',),
        }),
    )
    
    def id_short(self, obj):
        """Display shortened UUID."""
        return str(obj.id)[:8]
    id_short.short_description = 'ID'
    
    def status_badge(self, obj):
        """Display status with color badge."""
        colors = {
            'in_progress': '#FFA500',
            'completed': '#28A745',
            'failed': '#DC3545',
            'abandoned': '#6C757D',
        }
        color = colors.get(obj.status, '#6C757D')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def user_link(self, obj):
        """Display link to user."""
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.email)
        return '-'
    user_link.short_description = 'User'
    
    def organizer_link(self, obj):
        """Display link to organizer."""
        if obj.organizer:
            url = reverse('admin:organizers_organizer_change', args=[obj.organizer.id])
            return format_html('<a href="{}">{}</a>', url, obj.organizer.business_name)
        return '-'
    organizer_link.short_description = 'Organizer'
    
    def order_link(self, obj):
        """Display link to order."""
        if obj.primary_order:
            url = reverse('admin:events_order_change', args=[obj.primary_order.id])
            return format_html('<a href="{}">{}</a>', url, obj.primary_order.order_number)
        return '-'
    order_link.short_description = 'Order'
    
    def duration(self, obj):
        """Calculate and display flow duration."""
        if obj.completed_at:
            delta = obj.completed_at - obj.created_at
            seconds = int(delta.total_seconds())
            if seconds < 60:
                return f"{seconds}s"
            elif seconds < 3600:
                return f"{seconds // 60}m {seconds % 60}s"
            else:
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                return f"{hours}h {minutes}m"
        elif obj.failed_at:
            delta = obj.failed_at - obj.created_at
            seconds = int(delta.total_seconds())
            return f"{seconds}s (failed)"
        return "In progress"
    duration.short_description = 'Duration'
    
    def events_count(self, obj):
        """Display count of events in this flow."""
        count = obj.events.count()
        return format_html('<strong>{}</strong>', count)
    events_count.short_description = 'Events'
    
    def events_timeline(self, obj):
        """Display timeline of all events in this flow."""
        events = obj.events.all().order_by('created_at')
        if not events:
            return "No events yet"
        
        html = '<div style="font-family: monospace; background: #f5f5f5; padding: 15px; border-radius: 5px;">'
        
        for event in events:
            # Status icon
            icon = {
                'success': '✅',
                'failure': '❌',
                'info': 'ℹ️',
                'warning': '⚠️'
            }.get(event.status, '•')
            
            # Time since flow start
            delta = event.created_at - obj.created_at
            time_str = f"+{int(delta.total_seconds())}s"
            
            html += f'<div style="margin-bottom: 8px;">'
            html += f'<strong>{icon} {time_str}</strong> '
            html += f'<span style="color: #666;">[{event.source}]</span> '
            html += f'<strong>{event.step}</strong>'
            if event.message:
                html += f' - {event.message}'
            html += '</div>'
        
        html += '</div>'
        return mark_safe(html)
    events_timeline.short_description = 'Events Timeline'


@admin.register(PlatformFlowEvent)
class PlatformFlowEventAdmin(admin.ModelAdmin):
    """Admin interface for PlatformFlowEvent model."""
    
    list_display = [
        'id_short',
        'flow_link',
        'step',
        'status_badge',
        'source',
        'message_short',
        'created_at',
    ]
    
    list_filter = [
        'step',
        'status',
        'source',
        'created_at',
    ]
    
    search_fields = [
        'id',
        'flow__id',
        'message',
        'order__order_number',
    ]
    
    readonly_fields = [
        'id',
        'flow',
        'created_at',
        'updated_at',
        'metadata_display',
    ]
    
    fieldsets = (
        ('Event Information', {
            'fields': ('id', 'flow', 'step', 'status', 'source', 'created_at', 'updated_at')
        }),
        ('Details', {
            'fields': ('message',)
        }),
        ('Related Entities', {
            'fields': ('order', 'payment', 'email_log', 'celery_task_log')
        }),
        ('Metadata', {
            'fields': ('metadata_display',),
        }),
    )
    
    def id_short(self, obj):
        """Display shortened UUID."""
        return str(obj.id)[:8]
    id_short.short_description = 'ID'
    
    def flow_link(self, obj):
        """Display link to parent flow."""
        url = reverse('admin:core_platformflow_change', args=[obj.flow.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.flow.id)[:8])
    flow_link.short_description = 'Flow'
    
    def status_badge(self, obj):
        """Display status with color badge."""
        colors = {
            'success': '#28A745',
            'failure': '#DC3545',
            'info': '#17A2B8',
            'warning': '#FFC107',
        }
        color = colors.get(obj.status, '#6C757D')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def message_short(self, obj):
        """Display truncated message."""
        if obj.message:
            return obj.message[:50] + ('...' if len(obj.message) > 50 else '')
        return '-'
    message_short.short_description = 'Message'
    
    def metadata_display(self, obj):
        """Display formatted metadata."""
        if not obj.metadata:
            return "No metadata"
        
        import json
        formatted = json.dumps(obj.metadata, indent=2)
        return format_html('<pre style="background: #f5f5f5; padding: 10px;">{}</pre>', formatted)
    metadata_display.short_description = 'Metadata'


@admin.register(CeleryTaskLog)
class CeleryTaskLogAdmin(admin.ModelAdmin):
    """Admin interface for CeleryTaskLog model."""
    
    list_display = [
        'task_id_short',
        'task_name_short',
        'status_badge',
        'queue',
        'flow_link',
        'order_link',
        'duration_display',
        'created_at',
    ]
    
    list_filter = [
        'status',
        'task_name',
        'queue',
        'created_at',
    ]
    
    search_fields = [
        'task_id',
        'task_name',
        'order__order_number',
        'user__email',
        'error',
    ]
    
    readonly_fields = [
        'id',
        'task_id',
        'task_name',
        'status',
        'queue',
        'routing_key',
        'created_at',
        'updated_at',
        'args_display',
        'kwargs_display',
        'result_display',
        'error_display',
        'traceback_display',
    ]
    
    fieldsets = (
        ('Task Information', {
            'fields': ('id', 'task_id', 'task_name', 'status', 'created_at', 'updated_at')
        }),
        ('Queue Information', {
            'fields': ('queue', 'routing_key')
        }),
        ('Business Context', {
            'fields': ('flow', 'order', 'user')
        }),
        ('Arguments', {
            'fields': ('args_display', 'kwargs_display'),
            'classes': ('collapse',)
        }),
        ('Result', {
            'fields': ('result_display', 'duration_ms'),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_display', 'traceback_display'),
            'classes': ('collapse',)
        }),
    )
    
    def task_id_short(self, obj):
        """Display shortened task ID."""
        return obj.task_id[:8]
    task_id_short.short_description = 'Task ID'
    
    def task_name_short(self, obj):
        """Display shortened task name."""
        return obj.task_name.split('.')[-1] if '.' in obj.task_name else obj.task_name
    task_name_short.short_description = 'Task'
    
    def status_badge(self, obj):
        """Display status with color badge."""
        colors = {
            'started': '#17A2B8',
            'success': '#28A745',
            'failure': '#DC3545',
            'retry': '#FFC107',
        }
        color = colors.get(obj.status, '#6C757D')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def flow_link(self, obj):
        """Display link to flow."""
        if obj.flow:
            url = reverse('admin:core_platformflow_change', args=[obj.flow.id])
            return format_html('<a href="{}">{}</a>', url, str(obj.flow.id)[:8])
        return '-'
    flow_link.short_description = 'Flow'
    
    def order_link(self, obj):
        """Display link to order."""
        if obj.order:
            url = reverse('admin:events_order_change', args=[obj.order.id])
            return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
        return '-'
    order_link.short_description = 'Order'
    
    def duration_display(self, obj):
        """Display task duration."""
        if obj.duration_ms:
            if obj.duration_ms < 1000:
                return f"{obj.duration_ms}ms"
            else:
                return f"{obj.duration_ms / 1000:.2f}s"
        return '-'
    duration_display.short_description = 'Duration'
    
    def args_display(self, obj):
        """Display formatted args."""
        import json
        formatted = json.dumps(obj.args, indent=2)
        return format_html('<pre style="background: #f5f5f5; padding: 10px;">{}</pre>', formatted)
    args_display.short_description = 'Arguments'
    
    def kwargs_display(self, obj):
        """Display formatted kwargs."""
        import json
        formatted = json.dumps(obj.kwargs, indent=2)
        return format_html('<pre style="background: #f5f5f5; padding: 10px;">{}</pre>', formatted)
    kwargs_display.short_description = 'Keyword Arguments'
    
    def result_display(self, obj):
        """Display formatted result."""
        if not obj.result:
            return "No result"
        import json
        formatted = json.dumps(obj.result, indent=2)
        return format_html('<pre style="background: #e8f5e9; padding: 10px;">{}</pre>', formatted)
    result_display.short_description = 'Result'
    
    def error_display(self, obj):
        """Display error message."""
        if not obj.error:
            return "No error"
        return format_html('<pre style="background: #ffebee; padding: 10px; color: #c62828;">{}</pre>', obj.error)
    error_display.short_description = 'Error'
    
    def traceback_display(self, obj):
        """Display traceback."""
        if not obj.traceback:
            return "No traceback"
        return format_html('<pre style="background: #ffebee; padding: 10px; color: #c62828; font-size: 11px;">{}</pre>', obj.traceback)
    traceback_display.short_description = 'Traceback'

