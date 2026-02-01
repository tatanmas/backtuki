"""Admin configuration for migration system."""

from django.contrib import admin
from django.utils.html import format_html
from .models import MigrationJob, MigrationLog, MigrationCheckpoint, MigrationToken, BackupJob


@admin.register(MigrationJob)
class MigrationJobAdmin(admin.ModelAdmin):
    """Admin for migration jobs."""
    
    list_display = ('id', 'direction', 'status_badge', 'progress_bar', 'started_at', 'duration_display', 'executed_by')
    list_filter = ('status', 'direction', 'created_at')
    search_fields = ('id', 'source_url', 'target_url', 'executed_by__email')
    readonly_fields = ('id', 'created_at', 'updated_at', 'started_at', 'completed_at', 'duration_seconds')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('id', 'direction', 'status', 'executed_by')
        }),
        ('URLs y Autenticación', {
            'fields': ('source_url', 'target_url')
        }),
        ('Progreso', {
            'fields': ('progress_percent', 'current_step', 'models_completed', 'total_models', 
                      'records_processed', 'total_records', 'files_transferred', 'total_files')
        }),
        ('Archivo de Export', {
            'fields': ('export_file_path', 'export_file_size_mb')
        }),
        ('Tiempos', {
            'fields': ('started_at', 'completed_at', 'duration_seconds', 'created_at', 'updated_at')
        }),
        ('Errores', {
            'fields': ('error_message', 'error_traceback'),
            'classes': ('collapse',)
        }),
        ('Configuración', {
            'fields': ('config',),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status with color."""
        colors = {
            'pending': 'gray',
            'in_progress': 'blue',
            'completed': 'green',
            'failed': 'red',
            'cancelled': 'orange',
            'rolling_back': 'purple',
            'rolled_back': 'brown',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def progress_bar(self, obj):
        """Display progress bar."""
        return format_html(
            '<div style="width: 100px; background-color: #f0f0f0; border-radius: 3px;">'
            '<div style="width: {}%; background-color: #4CAF50; padding: 2px 0; text-align: center; color: white; border-radius: 3px;">{}</div>'
            '</div>',
            obj.progress_percent,
            f"{obj.progress_percent}%"
        )
    progress_bar.short_description = 'Progress'
    
    def duration_display(self, obj):
        """Display duration in human readable format."""
        if not obj.duration_seconds:
            return '-'
        minutes = obj.duration_seconds // 60
        seconds = obj.duration_seconds % 60
        return f"{minutes}m {seconds}s"
    duration_display.short_description = 'Duration'


@admin.register(MigrationLog)
class MigrationLogAdmin(admin.ModelAdmin):
    """Admin for migration logs."""
    
    list_display = ('timestamp', 'job', 'level_badge', 'message_short', 'model_name', 'record_count', 'duration_ms')
    list_filter = ('level', 'timestamp', 'model_name')
    search_fields = ('message', 'model_name', 'job__id')
    readonly_fields = ('id', 'job', 'timestamp')
    date_hierarchy = 'timestamp'
    
    def message_short(self, obj):
        """Display shortened message."""
        return obj.message[:100] + '...' if len(obj.message) > 100 else obj.message
    message_short.short_description = 'Message'
    
    def level_badge(self, obj):
        """Display level with color."""
        colors = {
            'debug': 'lightgray',
            'info': 'blue',
            'warning': 'orange',
            'error': 'red',
            'critical': 'darkred',
        }
        color = colors.get(obj.level, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.level.upper()
        )
    level_badge.short_description = 'Level'


@admin.register(MigrationCheckpoint)
class MigrationCheckpointAdmin(admin.ModelAdmin):
    """Admin for migration checkpoints."""
    
    list_display = ('name', 'environment', 'validity_badge', 'created_at', 'snapshot_size_mb', 'total_records', 'created_by')
    list_filter = ('is_valid', 'environment', 'created_at')
    search_fields = ('name', 'description', 'created_by__email')
    readonly_fields = ('id', 'created_at', 'updated_at', 'restored_at')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('id', 'name', 'description', 'environment', 'created_by')
        }),
        ('Archivo de Snapshot', {
            'fields': ('snapshot_file_path', 'snapshot_size_mb')
        }),
        ('Estadísticas', {
            'fields': ('total_models', 'total_records', 'total_files', 'database_version')
        }),
        ('Estado', {
            'fields': ('is_valid', 'used_for_restore', 'restored_at', 'expires_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def validity_badge(self, obj):
        """Display validity status."""
        if not obj.is_valid:
            return format_html('<span style="color: red;">✗ Invalid</span>')
        if obj.is_expired:
            return format_html('<span style="color: orange;">⚠ Expired</span>')
        if obj.used_for_restore:
            return format_html('<span style="color: blue;">Used</span>')
        return format_html('<span style="color: green;">✓ Valid</span>')
    validity_badge.short_description = 'Validity'


@admin.register(MigrationToken)
class MigrationTokenAdmin(admin.ModelAdmin):
    """Admin for migration tokens."""
    
    list_display = ('token_short', 'description', 'permissions', 'validity_status', 'usage_count', 'expires_at', 'created_by')
    list_filter = ('permissions', 'is_single_use', 'created_at')
    search_fields = ('description', 'token', 'created_by__email')
    readonly_fields = ('id', 'token', 'created_at', 'used_at', 'last_used_at', 'last_used_ip', 'usage_count')
    
    fieldsets = (
        ('Token', {
            'fields': ('id', 'token', 'description', 'permissions')
        }),
        ('Seguridad', {
            'fields': ('allowed_ips', 'allowed_domains', 'is_single_use')
        }),
        ('Expiración', {
            'fields': ('expires_at', 'revoked_at', 'revoked_by')
        }),
        ('Uso', {
            'fields': ('usage_count', 'used_at', 'last_used_at', 'last_used_ip')
        }),
        ('Auditoría', {
            'fields': ('created_by', 'created_at')
        }),
    )
    
    def token_short(self, obj):
        """Display shortened token."""
        return f"{obj.token[:16]}..."
    token_short.short_description = 'Token'
    
    def validity_status(self, obj):
        """Display validity status."""
        if obj.revoked_at:
            return format_html('<span style="color: red;">✗ Revoked</span>')
        if not obj.is_valid:
            return format_html('<span style="color: orange;">✗ Expired/Used</span>')
        return format_html('<span style="color: green;">✓ Valid</span>')
    validity_status.short_description = 'Status'


@admin.register(BackupJob)
class BackupJobAdmin(admin.ModelAdmin):
    """Admin for backup/restore jobs."""
    
    list_display = ('id', 'original_filename', 'status_badge', 'progress_bar', 'file_size_mb', 
                   'sql_records_restored', 'media_files_restored', 'created_at', 'uploaded_by')
    list_filter = ('status', 'restore_sql', 'restore_media', 'created_at')
    search_fields = ('id', 'original_filename', 'uploaded_by__email')
    readonly_fields = ('id', 'file_size_mb', 'backup_metadata', 'sql_records_restored', 
                      'media_files_restored', 'media_size_mb', 'safety_backup_path',
                      'started_at', 'completed_at', 'duration_seconds', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Archivo de Backup', {
            'fields': ('id', 'backup_file', 'original_filename', 'file_size_mb', 'uploaded_by')
        }),
        ('Estado', {
            'fields': ('status', 'progress_percent', 'current_step')
        }),
        ('Opciones de Restore', {
            'fields': ('restore_sql', 'restore_media', 'create_backup_before')
        }),
        ('Resultados', {
            'fields': ('sql_records_restored', 'media_files_restored', 'media_size_mb', 
                      'safety_backup_path', 'backup_metadata')
        }),
        ('Tiempos', {
            'fields': ('started_at', 'completed_at', 'duration_seconds', 'created_at', 'updated_at')
        }),
        ('Errores', {
            'fields': ('error_message', 'error_traceback'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status with color."""
        colors = {
            'uploaded': 'gray',
            'validating': 'blue',
            'validated': 'lightblue',
            'restoring': 'orange',
            'completed': 'green',
            'failed': 'red',
            'cancelled': 'darkgray',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def progress_bar(self, obj):
        """Display progress bar."""
        return format_html(
            '<div style="width: 100px; background-color: #f0f0f0; border-radius: 3px;">'
            '<div style="width: {}%; background-color: #FF6B35; padding: 2px 0; text-align: center; color: white; border-radius: 3px; font-size: 11px;">{}</div>'
            '</div>',
            obj.progress_percent,
            f"{obj.progress_percent}%"
        )
    progress_bar.short_description = 'Progress'
