from django.contrib import admin
from .models import TravelGuide


@admin.register(TravelGuide)
class TravelGuideAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'destination', 'template', 'status', 'published_at', 'display_order')
    list_filter = ('status', 'template')
    search_fields = ('title', 'slug', 'excerpt')
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ('destination',)
