"""Admin configuration for organizers app."""

from django.contrib import admin
from .models import (
    Organizer,
    OrganizerOnboarding,
    BillingDetails,
    BankingDetails,
    OrganizerUser,
    OrganizerSubscription
)


@admin.register(Organizer)
class OrganizerAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'contact_email', 'status', 'onboarding_completed')
    list_filter = ('status', 'onboarding_completed', 'has_events_module', 'has_accommodation_module', 'has_experience_module')
    search_fields = ('name', 'slug', 'contact_email', 'representative_name')
    readonly_fields = ('id', 'organizer_id', 'created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'logo', 'website')
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'contact_phone', 'address', 'city', 'country')
        }),
        ('Organization Details', {
            'fields': ('organization_size', 'status', 'onboarding_completed')
        }),
        ('Module Activation', {
            'fields': ('has_events_module', 'has_accommodation_module', 'has_experience_module')
        }),
        ('Representative Information', {
            'fields': ('representative_name', 'representative_email', 'representative_phone')
        }),
        ('System Information', {
            'fields': ('id', 'organizer_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrganizerOnboarding)
class OrganizerOnboardingAdmin(admin.ModelAdmin):
    list_display = ('organizer', 'completed_step', 'is_completed')
    list_filter = ('is_completed', 'completed_step')
    search_fields = ('organizer__name', 'contact_name', 'contact_email')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(BillingDetails)
class BillingDetailsAdmin(admin.ModelAdmin):
    list_display = ('organizer', 'person_type', 'tax_name', 'tax_id')
    list_filter = ('person_type', 'document_type')
    search_fields = ('organizer__name', 'tax_name', 'tax_id')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(BankingDetails)
class BankingDetailsAdmin(admin.ModelAdmin):
    list_display = ('organizer', 'bank_name', 'account_type', 'account_holder')
    list_filter = ('account_type',)
    search_fields = ('organizer__name', 'bank_name', 'account_holder')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(OrganizerUser)
class OrganizerUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'organizer', 'is_admin')
    list_filter = ('is_admin', 'can_manage_events', 'can_manage_accommodations', 'can_manage_experiences')
    search_fields = ('user__email', 'organizer__name')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(OrganizerSubscription)
class OrganizerSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('organizer', 'plan', 'status', 'start_date', 'end_date')
    list_filter = ('plan', 'status')
    search_fields = ('organizer__name',)
    readonly_fields = ('id', 'created_at', 'updated_at') 