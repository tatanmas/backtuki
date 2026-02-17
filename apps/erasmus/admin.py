from django.contrib import admin
from .models import ErasmusLead, ErasmusTrackingLink, ErasmusExtraField, ErasmusDestinationGuide


@admin.register(ErasmusLead)
class ErasmusLeadAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "stay_reason", "country", "city", "has_accommodation_in_chile", "wants_rumi4students_contact", "email", "phone_number", "university", "source_slug", "created_at")
    list_filter = ("stay_reason", "source_slug", "country", "has_accommodation_in_chile", "wants_rumi4students_contact", "created_at")
    search_fields = ("first_name", "last_name", "email", "instagram", "university", "stay_reason_detail", "country", "city")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(ErasmusDestinationGuide)
class ErasmusDestinationGuideAdmin(admin.ModelAdmin):
    list_display = ("title", "destination_slug", "order", "is_active", "file_url")
    list_filter = ("destination_slug", "is_active")
    search_fields = ("title", "destination_slug")
    ordering = ("destination_slug", "order")


@admin.register(ErasmusTrackingLink)
class ErasmusTrackingLinkAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(ErasmusExtraField)
class ErasmusExtraFieldAdmin(admin.ModelAdmin):
    list_display = ("label", "field_key", "type", "required", "order", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("label", "field_key")
    ordering = ("order",)
