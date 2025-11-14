"""
🚀 ENTERPRISE VALIDATION SERIALIZERS
Serializers para el sistema de validación enterprise
"""

from rest_framework import serializers
from .models import ValidatorSession, TicketValidationLog, TicketNote, EventValidationStats
from apps.events.models import Ticket, Event
from apps.organizers.models import Organizer


class ValidatorSessionSerializer(serializers.ModelSerializer):
    """Serializer para sesiones de validador"""
    
    event_title = serializers.CharField(source='event.title', read_only=True)
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)
    duration_minutes = serializers.SerializerMethodField()
    success_rate = serializers.SerializerMethodField()
    throughput_per_hour = serializers.SerializerMethodField()
    
    class Meta:
        model = ValidatorSession
        fields = [
            'id', 'validator_name', 'event', 'event_title', 
            'organizer', 'organizer_name', 'start_time', 'end_time',
            'is_active', 'total_scans', 'successful_validations',
            'failed_validations', 'tickets_checked_in', 'duration_minutes',
            'success_rate', 'throughput_per_hour', 'device_info', 'location'
        ]
        read_only_fields = [
            'id', 'start_time', 'total_scans', 'successful_validations',
            'failed_validations', 'tickets_checked_in'
        ]
    
    def get_duration_minutes(self, obj):
        """Duración en minutos"""
        duration = obj.duration
        if duration:
            return round(duration.total_seconds() / 60, 1)
        return None
    
    def get_success_rate(self, obj):
        """Tasa de éxito"""
        return round(obj.success_rate, 2)
    
    def get_throughput_per_hour(self, obj):
        """Throughput por hora"""
        return round(obj.throughput_per_hour, 1)


class TicketValidationLogSerializer(serializers.ModelSerializer):
    """Serializer para logs de validación"""
    
    ticket_number = serializers.CharField(source='ticket.ticket_number', read_only=True)
    validator_name = serializers.CharField(source='validator_session.validator_name', read_only=True)
    event_title = serializers.CharField(source='validator_session.event.title', read_only=True)
    
    class Meta:
        model = TicketValidationLog
        fields = [
            'id', 'ticket', 'ticket_number', 'validator_session',
            'validator_name', 'event_title', 'action', 'status',
            'message', 'created_at', 'scan_time_ms', 'qr_data',
            'device_location', 'metadata', 'error_code', 'error_details'
        ]
        read_only_fields = ['id', 'created_at']


class TicketNoteSerializer(serializers.ModelSerializer):
    """Serializer para notas de tickets"""
    
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    ticket_number = serializers.CharField(source='ticket.ticket_number', read_only=True)
    validator_name = serializers.CharField(source='validator_session.validator_name', read_only=True)
    
    class Meta:
        model = TicketNote
        fields = [
            'id', 'ticket', 'ticket_number', 'user', 'user_name',
            'validator_session', 'validator_name', 'note_type',
            'title', 'content', 'is_important', 'is_resolved',
            'attachments', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class EventValidationStatsSerializer(serializers.ModelSerializer):
    """Serializer para estadísticas de validación"""
    
    event_title = serializers.CharField(source='event.title', read_only=True)
    scan_rate = serializers.SerializerMethodField()
    validation_success_rate = serializers.SerializerMethodField()
    checkin_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = EventValidationStats
        fields = [
            'id', 'event', 'event_title', 'total_tickets',
            'tickets_scanned', 'tickets_validated', 'tickets_checked_in',
            'tickets_rejected', 'first_scan_time', 'last_scan_time',
            'average_scan_time_ms', 'peak_throughput_per_minute',
            'active_validators', 'total_validator_sessions',
            'scan_rate', 'validation_success_rate', 'checkin_rate',
            'last_updated'
        ]
        read_only_fields = ['id', 'last_updated']
    
    def get_scan_rate(self, obj):
        return round(obj.scan_rate, 2)
    
    def get_validation_success_rate(self, obj):
        return round(obj.validation_success_rate, 2)
    
    def get_checkin_rate(self, obj):
        return round(obj.checkin_rate, 2)


class TicketDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado para tickets con toda la información"""
    
    attendee_name = serializers.SerializerMethodField()
    event_info = serializers.SerializerMethodField()
    order_info = serializers.SerializerMethodField()
    tier_info = serializers.SerializerMethodField()
    validation_history = serializers.SerializerMethodField()
    notes = TicketNoteSerializer(many=True, read_only=True)
    
    class Meta:
        model = Ticket
        fields = [
            'id', 'ticket_number', 'first_name', 'last_name',
            'attendee_name', 'email', 'status', 'check_in_status',
            'checked_in', 'check_in_time', 'check_in_by',
            'form_data', 'event_info', 'order_info', 'tier_info',
            'validation_history', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_attendee_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    
    def get_event_info(self, obj):
        event = obj.order_item.order.event
        return {
            'id': event.id,
            'title': event.title,
            'start_date': event.start_date,
            'end_date': event.end_date,
            'location': {
                'name': event.location.name if event.location else None,
                'address': event.location.address if event.location else None
            } if hasattr(event, 'location') else None
        }
    
    def get_order_info(self, obj):
        order = obj.order_item.order
        return {
            'id': order.id,
            'purchase_date': order.created_at,
            'total_amount': float(order.total_amount),
            'payment_status': order.payment_status if hasattr(order, 'payment_status') else None
        }
    
    def get_tier_info(self, obj):
        tier = obj.order_item.ticket_tier
        return {
            'id': tier.id,
            'name': tier.name,
            'price': float(tier.price),
            'description': tier.description if hasattr(tier, 'description') else None
        }
    
    def get_validation_history(self, obj):
        """Últimas 10 validaciones del ticket"""
        logs = obj.validation_logs.all()[:10]
        return TicketValidationLogSerializer(logs, many=True).data


class ValidationRequestSerializer(serializers.Serializer):
    """Serializer para request de validación"""
    
    ticket_number = serializers.CharField(max_length=50)
    session_id = serializers.IntegerField()
    qr_data = serializers.CharField(required=False, allow_blank=True)
    scan_time_ms = serializers.IntegerField(required=False, default=0)
    device_location = serializers.JSONField(required=False, default=dict)


class CheckinRequestSerializer(serializers.Serializer):
    """Serializer para request de check-in"""
    
    session_id = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True)
    device_location = serializers.JSONField(required=False, default=dict)


class StartSessionRequestSerializer(serializers.Serializer):
    """Serializer para iniciar sesión de validador"""
    
    validator_name = serializers.CharField(max_length=100)
    event_id = serializers.IntegerField()
    device_info = serializers.JSONField(required=False, default=dict)
    location = serializers.JSONField(required=False, default=dict)


