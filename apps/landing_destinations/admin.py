from django.contrib import admin
from .models import LandingDestination, LandingDestinationExperience, LandingDestinationEvent


class LandingDestinationExperienceInline(admin.TabularInline):
    model = LandingDestinationExperience
    extra = 0
    raw_id_fields = ()


class LandingDestinationEventInline(admin.TabularInline):
    model = LandingDestinationEvent
    extra = 0
    raw_id_fields = ()


@admin.register(LandingDestination)
class LandingDestinationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "country", "region", "is_active", "latitude", "longitude")
    list_filter = ("is_active", "country")
    search_fields = ("name", "slug", "region")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [LandingDestinationExperienceInline, LandingDestinationEventInline]
