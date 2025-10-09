from django.contrib import admin
from .models import Event, TicketHolderReservation

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'organizer', 'status', 'start_date', 'end_date', 'location', 'category', 'featured', 'created_at', 'updated_at'
    )
    search_fields = ('title', 'organizer__name', 'category__name', 'location__name', 'description')
    list_filter = ('organizer', 'status', 'category', 'featured', 'start_date', 'end_date')
    readonly_fields = ('created_at', 'updated_at', 'slug')
    ordering = ('-start_date',)


@admin.register(TicketHolderReservation)
class TicketHolderReservationAdmin(admin.ModelAdmin):
    """
    🚀 ENTERPRISE: Admin interface for debugging ticket holder reservations
    """
    list_display = (
        'order', 'ticket_tier', 'holder_index', 'first_name', 'last_name', 'email', 'created_at'
    )
    search_fields = ('order__order_number', 'first_name', 'last_name', 'email', 'ticket_tier__name')
    list_filter = ('ticket_tier', 'created_at', 'order__status')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order', 'ticket_tier') 