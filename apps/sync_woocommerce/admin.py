"""
Configuración del admin para sincronización WooCommerce
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import SyncConfiguration, SyncExecution, SyncCredentials


@admin.register(SyncConfiguration)
class SyncConfigurationAdmin(admin.ModelAdmin):
    """Admin para configuraciones de sincronización"""
    
    list_display = [
        'name', 'woocommerce_product_id', 'event_name', 'organizer_email',
        'status', 'frequency', 'success_rate_display', 'last_sync_display',
        'actions_display'
    ]
    list_filter = [
        'status', 'frequency', 'created_at', 'last_sync_status'
    ]
    search_fields = [
        'name', 'event_name', 'organizer_email', 'woocommerce_product_id'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'last_sync_at', 'last_sync_status',
        'total_syncs', 'successful_syncs', 'django_event_id',
        'django_organizer_id', 'django_form_id', 'success_rate_display'
    ]
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'id')
        }),
        ('Configuración WooCommerce', {
            'fields': ('woocommerce_product_id',)
        }),
        ('Configuración del Evento', {
            'fields': (
                'event_name', 'event_description', 'event_start_date', 'event_end_date'
            )
        }),
        ('Organizador', {
            'fields': ('organizer_email', 'organizer_name')
        }),
        ('Configuración Financiera', {
            'fields': ('service_fee_percentage',)
        }),
        ('Configuración de Sincronización', {
            'fields': ('frequency', 'status')
        }),
        ('Estadísticas', {
            'fields': (
                'total_syncs', 'successful_syncs', 'success_rate_display',
                'last_sync_at', 'last_sync_status'
            ),
            'classes': ('collapse',)
        }),
        ('Referencias Django', {
            'fields': (
                'django_event_id', 'django_organizer_id', 'django_form_id'
            ),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def success_rate_display(self, obj):
        """Mostrar tasa de éxito con colores"""
        rate = obj.success_rate
        if rate >= 90:
            color = 'green'
        elif rate >= 70:
            color = 'orange'
        else:
            color = 'red'
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color, rate
        )
    success_rate_display.short_description = 'Tasa de Éxito'
    
    def last_sync_display(self, obj):
        """Mostrar última sincronización con estado"""
        if not obj.last_sync_at:
            return format_html('<span style="color: gray;">Nunca</span>')
        
        time_diff = timezone.now() - obj.last_sync_at
        if time_diff.days > 7:
            color = 'red'
            text = f'Hace {time_diff.days} días'
        elif time_diff.days > 1:
            color = 'orange'
            text = f'Hace {time_diff.days} días'
        else:
            color = 'green'
            text = 'Reciente'
        
        status_color = 'green' if obj.last_sync_status == 'success' else 'red'
        
        return format_html(
            '<span style="color: {};">{}</span><br>'
            '<small style="color: {};">{}</small>',
            color, text, status_color, obj.last_sync_status or 'N/A'
        )
    last_sync_display.short_description = 'Última Sincronización'
    
    def actions_display(self, obj):
        """Mostrar acciones disponibles"""
        actions = []
        
        if obj.status == 'active':
            actions.append(
                f'<a href="#" onclick="triggerSync(\'{obj.id}\')" '
                f'style="color: blue;">▶ Sincronizar</a>'
            )
        
        executions_url = reverse('admin:sync_woocommerce_syncexecution_changelist')
        actions.append(
            f'<a href="{executions_url}?configuration__id__exact={obj.id}" '
            f'style="color: green;">📊 Ver Ejecuciones</a>'
        )
        
        return format_html('<br>'.join(actions))
    actions_display.short_description = 'Acciones'
    
    class Media:
        js = ('admin/js/sync_actions.js',)


@admin.register(SyncExecution)
class SyncExecutionAdmin(admin.ModelAdmin):
    """Admin para ejecuciones de sincronización"""
    
    list_display = [
        'configuration_name', 'status_display', 'trigger', 'started_at',
        'duration_display', 'results_display'
    ]
    list_filter = [
        'status', 'trigger', 'started_at', 'configuration__name'
    ]
    search_fields = [
        'configuration__name', 'error_message', 'celery_task_id'
    ]
    readonly_fields = [
        'id', 'configuration', 'started_at', 'finished_at', 'duration_seconds',
        'celery_task_id', 'triggered_by'
    ]
    fieldsets = (
        ('Información Básica', {
            'fields': ('id', 'configuration', 'status', 'trigger')
        }),
        ('Tiempos', {
            'fields': ('started_at', 'finished_at', 'duration_seconds')
        }),
        ('Resultados', {
            'fields': (
                'orders_processed', 'tickets_processed',
                'orders_created', 'orders_updated',
                'tickets_created', 'tickets_updated'
            )
        }),
        ('Error', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('celery_task_id', 'triggered_by'),
            'classes': ('collapse',)
        })
    )
    
    def configuration_name(self, obj):
        """Mostrar nombre de configuración con enlace"""
        url = reverse('admin:sync_woocommerce_syncconfiguration_change', args=[obj.configuration.id])
        return format_html('<a href="{}">{}</a>', url, obj.configuration.name)
    configuration_name.short_description = 'Configuración'
    
    def status_display(self, obj):
        """Mostrar estado con colores"""
        colors = {
            'success': 'green',
            'failed': 'red',
            'running': 'blue',
            'pending': 'orange',
            'cancelled': 'gray'
        }
        color = colors.get(obj.status, 'black')
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = 'Estado'
    
    def duration_display(self, obj):
        """Mostrar duración formateada"""
        if not obj.duration_seconds:
            return '-'
        
        seconds = obj.duration_seconds
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds}s"
        else:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            return f"{hours}h {remaining_minutes}m"
    duration_display.short_description = 'Duración'
    
    def results_display(self, obj):
        """Mostrar resumen de resultados"""
        if obj.status != 'success':
            return '-'
        
        return format_html(
            '<strong>Órdenes:</strong> {} (+{} nuevas)<br>'
            '<strong>Tickets:</strong> {} (+{} nuevos)',
            obj.orders_processed, obj.orders_created,
            obj.tickets_processed, obj.tickets_created
        )
    results_display.short_description = 'Resultados'


@admin.register(SyncCredentials)
class SyncCredentialsAdmin(admin.ModelAdmin):
    """Admin para credenciales de sincronización"""
    
    list_display = [
        'name', 'ssh_host', 'mysql_database', 'is_active', 'is_default', 'created_at'
    ]
    list_filter = ['is_active', 'is_default', 'created_at']
    search_fields = ['name', 'ssh_host', 'mysql_database']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'id')
        }),
        ('Configuración SSH', {
            'fields': ('ssh_host', 'ssh_port', 'ssh_username')
        }),
        ('Configuración MySQL', {
            'fields': ('mysql_host', 'mysql_port', 'mysql_database', 'mysql_username')
        }),
        ('Estado', {
            'fields': ('is_active', 'is_default')
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


# Personalización del admin site
admin.site.site_header = "🚀 TUKI - Administración Enterprise"
admin.site.site_title = "TUKI Admin"
admin.site.index_title = "Panel de Administración"
