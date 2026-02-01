"""
🚀 ENTERPRISE MEDIA LIBRARY ADMIN
"""

from django.contrib import admin
from apps.media.models import MediaAsset, MediaUsage


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'original_filename',
        'scope',
        'organizer',
        'uploaded_by',
        'size_mb',
        'width',
        'height',
        'created_at',
        'deleted_at'
    ]
    list_filter = ['scope', 'content_type', 'deleted_at', 'created_at']
    search_fields = ['original_filename', 'organizer__name']
    readonly_fields = [
        'id',
        'sha256',
        'size_bytes',
        'width',
        'height',
        'created_at',
        'updated_at'
    ]
    
    def size_mb(self, obj):
        return obj.size_mb
    size_mb.short_description = 'Size (MB)'


@admin.register(MediaUsage)
class MediaUsageAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'asset',
        'content_type',
        'object_id',
        'field_name',
        'created_at',
        'deleted_at'
    ]
    list_filter = ['content_type', 'deleted_at', 'created_at']
    search_fields = ['asset__original_filename']
    readonly_fields = ['id', 'created_at', 'updated_at']

