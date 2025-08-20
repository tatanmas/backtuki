from django.contrib import admin
from .models import Event

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'organizer', 'status', 'start_date', 'end_date', 'location', 'category', 'featured', 'created_at', 'updated_at'
    )
    search_fields = ('title', 'organizer__name', 'category__name', 'location__name', 'description')
    list_filter = ('organizer', 'status', 'category', 'featured', 'start_date', 'end_date')
    readonly_fields = ('created_at', 'updated_at', 'slug')
    ordering = ('-start_date',) 