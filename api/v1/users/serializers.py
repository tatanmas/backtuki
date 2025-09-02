from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.events.models import Order

User = get_user_model()


class UserReservationSerializer(serializers.ModelSerializer):
    """Serializer para reservas de usuario"""
    
    eventId = serializers.CharField(source='event.id', read_only=True)
    eventTitle = serializers.CharField(source='event.title', read_only=True)
    eventImage = serializers.SerializerMethodField()
    eventDate = serializers.SerializerMethodField()
    eventTime = serializers.SerializerMethodField()
    location = serializers.CharField(source='event.location.name', read_only=True)
    orderId = serializers.CharField(source='order_number', read_only=True)
    totalAmount = serializers.DecimalField(source='total', max_digits=10, decimal_places=2, read_only=True)
    ticketCount = serializers.SerializerMethodField()
    tickets = serializers.SerializerMethodField()
    purchaseDate = serializers.DateTimeField(source='created_at', read_only=True)
    attendees = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'orderId', 'eventId', 'eventTitle', 'eventImage',
            'eventDate', 'eventTime', 'location', 'status',
            'totalAmount', 'currency', 'ticketCount', 'tickets',
            'purchaseDate', 'attendees'
        ]
    
    def get_eventImage(self, obj):
        """Obtener imagen del evento"""
        if obj.event and obj.event.images.exists():
            return obj.event.images.first().url
        return None
    
    def get_eventDate(self, obj):
        """Formatear fecha del evento"""
        if obj.event and obj.event.start_date:
            return obj.event.start_date.strftime('%d %B %Y')
        return None
    
    def get_eventTime(self, obj):
        """Formatear hora del evento"""
        if obj.event and obj.event.start_date:
            return obj.event.start_date.strftime('%H:%M')
        return None
    
    def get_ticketCount(self, obj):
        """Contar total de tickets"""
        return sum(item.quantity for item in obj.items.all())
    
    def get_tickets(self, obj):
        """Obtener detalles de tickets"""
        tickets = []
        for item in obj.items.all():
            tickets.append({
                'id': item.id,
                'tierName': item.ticket_tier.name if item.ticket_tier else 'General',
                'quantity': item.quantity,
                'unitPrice': float(item.unit_price)
            })
        return tickets
    
    def get_attendees(self, obj):
        """Obtener información de asistentes"""
        attendees = []
        if obj.first_name or obj.last_name:
            attendees.append({
                'name': f"{obj.first_name} {obj.last_name}".strip(),
                'email': obj.email
            })
        return attendees