"""Admin configuration for experiences app."""

from django.contrib import admin
from .models import Experience, TourLanguage, TourInstance, TourBooking, OrganizerCredit


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    """Admin interface for Experience model."""
    list_display = ('title', 'organizer', 'type', 'is_free_tour', 'status', 'created_at')
    list_filter = ('status', 'type', 'is_free_tour', 'organizer')
    search_fields = ('title', 'description', 'organizer__name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'description', 'short_description', 'type', 'status')
        }),
        ('Organizer', {
            'fields': ('organizer',)
        }),
        ('Free Tour Settings', {
            'fields': ('is_free_tour', 'credit_per_person', 'sales_cutoff_hours', 'recurrence_pattern'),
            'classes': ('collapse',)
        }),
        ('Pricing', {
            'fields': ('price',)
        }),
        ('Location', {
            'fields': ('location_name', 'location_address', 'location_latitude', 'location_longitude')
        }),
        ('Details', {
            'fields': ('duration_minutes', 'max_participants', 'min_participants', 'included', 'not_included', 'requirements', 'itinerary')
        }),
        ('Media', {
            'fields': ('images',)
        }),
        ('Metadata', {
            'fields': ('categories', 'tags', 'views_count')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TourLanguage)
class TourLanguageAdmin(admin.ModelAdmin):
    """Admin interface for TourLanguage model."""
    list_display = ('experience', 'language_code', 'title', 'is_active', 'created_at')
    list_filter = ('language_code', 'is_active')
    search_fields = ('experience__title', 'title', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(TourInstance)
class TourInstanceAdmin(admin.ModelAdmin):
    """Admin interface for TourInstance model."""
    list_display = ('experience', 'start_datetime', 'language', 'status', 'max_capacity', 'created_at')
    list_filter = ('status', 'language', 'experience')
    search_fields = ('experience__title', 'notes')
    readonly_fields = ('id', 'created_at', 'updated_at')
    date_hierarchy = 'start_datetime'


@admin.register(TourBooking)
class TourBookingAdmin(admin.ModelAdmin):
    """Admin interface for TourBooking model."""
    list_display = ('first_name', 'last_name', 'email', 'tour_instance', 'participants_count', 'status', 'created_at')
    list_filter = ('status', 'tour_instance__experience', 'tour_instance__language')
    search_fields = ('first_name', 'last_name', 'email', 'phone')
    readonly_fields = ('id', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(OrganizerCredit)
class OrganizerCreditAdmin(admin.ModelAdmin):
    """Admin interface for OrganizerCredit model."""
    list_display = ('organizer', 'tour_booking', 'amount', 'is_billed', 'billed_at', 'created_at')
    list_filter = ('is_billed', 'organizer')
    search_fields = ('organizer__name', 'tour_booking__first_name', 'tour_booking__last_name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

