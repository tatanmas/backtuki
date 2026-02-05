"""Django admin for creators app."""

from django.contrib import admin
from .models import CreatorProfile, CreatorRecommendedExperience, PlatformLandingSlot


@admin.register(PlatformLandingSlot)
class PlatformLandingSlotAdmin(admin.ModelAdmin):
    list_display = ('slot_key', 'asset', 'created_at')
    list_filter = ('slot_key',)
    raw_id_fields = ('asset',)


@admin.register(CreatorProfile)
class CreatorProfileAdmin(admin.ModelAdmin):
    list_display = ('slug', 'display_name', 'user', 'is_approved', 'created_at')
    list_filter = ('is_approved',)
    search_fields = ('slug', 'display_name', 'user__email')
    raw_id_fields = ('user',)


@admin.register(CreatorRecommendedExperience)
class CreatorRecommendedExperienceAdmin(admin.ModelAdmin):
    list_display = ('creator', 'experience', 'order')
    list_filter = ('creator',)
    raw_id_fields = ('creator', 'experience')
