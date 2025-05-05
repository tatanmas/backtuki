from django.contrib import admin
from .models import Organizer, OrganizerUser

@admin.register(Organizer)
class OrganizerAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'schema_name', 'status', 'created_at')
    search_fields = ('name', 'description', 'schema_name')
    list_filter = ('status', 'created_at')
    readonly_fields = ('id', 'schema_name', 'created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'description', 'logo', 'status')
        }),
        ('Technical Details', {
            'fields': ('schema_name', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(OrganizerUser)
class OrganizerUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'organizer', 'created_at')
    search_fields = ('user__email', 'user__username', 'organizer__name')
    list_filter = ('created_at',)
    raw_id_fields = ('user', 'organizer')
    readonly_fields = ('created_at', 'updated_at') 