"""Admin configuration for terminal app."""

from django.contrib import admin
from .models import TerminalCompany, TerminalRoute, TerminalTrip, TerminalExcelUpload


@admin.register(TerminalCompany)
class TerminalCompanyAdmin(admin.ModelAdmin):
    """Admin for TerminalCompany."""
    
    list_display = ['name', 'booking_method', 'is_active', 'created_at']
    list_filter = ['is_active', 'contact_method', 'booking_method']
    search_fields = ['name', 'phone', 'email']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'phone', 'email', 'website', 'logo', 'contact_method')
        }),
        ('Booking Configuration', {
            'fields': ('booking_url', 'booking_phone', 'booking_whatsapp', 'booking_method')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TerminalRoute)
class TerminalRouteAdmin(admin.ModelAdmin):
    """Admin for TerminalRoute."""
    
    list_display = ['origin', 'destination', 'duration', 'distance']
    search_fields = ['origin', 'destination']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('Route Information', {
            'fields': ('origin', 'destination', 'duration', 'distance')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TerminalTrip)
class TerminalTripAdmin(admin.ModelAdmin):
    """Admin for TerminalTrip."""
    
    list_display = ['company', 'route', 'date', 'trip_type', 'departure_time', 'arrival_time', 'status', 'is_active']
    list_filter = ['trip_type', 'status', 'is_active', 'date', 'company']
    search_fields = ['company__name', 'route__origin', 'route__destination', 'license_plate']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'date'
    fieldsets = (
        ('Trip Information', {
            'fields': ('company', 'route', 'trip_type', 'date', 'departure_time', 'arrival_time')
        }),
        ('Bus Details', {
            'fields': ('platform', 'license_plate', 'observations')
        }),
        ('Pricing & Status', {
            'fields': ('price', 'currency', 'status', 'is_active')
        }),
        ('Seats (v1 - not used)', {
            'fields': ('total_seats', 'available_seats'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TerminalExcelUpload)
class TerminalExcelUploadAdmin(admin.ModelAdmin):
    """Admin for TerminalExcelUpload."""
    
    list_display = ['file_name', 'upload_type', 'date_range_start', 'date_range_end', 'status', 'trips_created', 'trips_updated', 'created_at']
    list_filter = ['status', 'upload_type', 'created_at']
    search_fields = ['file_name', 'uploaded_by__email']
    readonly_fields = ['id', 'created_at', 'updated_at', 'processed_sheets', 'errors']
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Upload Information', {
            'fields': ('file_name', 'file_path', 'upload_type', 'date_range_start', 'date_range_end', 'status')
        }),
        ('Processing Results', {
            'fields': ('trips_created', 'trips_updated', 'processed_sheets', 'errors')
        }),
        ('Metadata', {
            'fields': ('uploaded_by', 'id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

