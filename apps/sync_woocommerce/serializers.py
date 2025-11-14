"""
Serializers para la API de sincronización WooCommerce
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import SyncConfiguration, SyncExecution, SyncCredentials


class SyncConfigurationSerializer(serializers.ModelSerializer):
    """Serializer para configuraciones de sincronización"""
    
    success_rate = serializers.ReadOnlyField()
    is_due_for_sync = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = SyncConfiguration
        fields = [
            'id', 'name', 'woocommerce_product_id', 'event_name',
            'organizer_email', 'organizer_name', 'service_fee_percentage',
            'frequency', 'status', 'event_description', 'event_start_date',
            'event_end_date', 'created_at', 'updated_at', 'last_sync_at',
            'last_sync_status', 'total_syncs', 'successful_syncs',
            'success_rate', 'is_due_for_sync', 'created_by_name',
            'django_event_id', 'django_organizer_id', 'django_form_id'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'last_sync_at',
            'last_sync_status', 'total_syncs', 'successful_syncs',
            'success_rate', 'is_due_for_sync', 'created_by_name',
            'django_event_id', 'django_organizer_id', 'django_form_id'
        ]
    
    def validate_service_fee_percentage(self, value):
        """Validar porcentaje de cargo por servicio"""
        if value < 0 or value > 100:
            raise serializers.ValidationError(
                "El porcentaje debe estar entre 0 y 100"
            )
        return value
    
    def validate(self, data):
        """Validaciones adicionales"""
        # Validar fechas
        if data.get('event_start_date') and data.get('event_end_date'):
            if data['event_start_date'] >= data['event_end_date']:
                raise serializers.ValidationError({
                    'event_end_date': 'La fecha de fin debe ser posterior a la fecha de inicio'
                })
        
        return data


class SyncConfigurationCreateSerializer(SyncConfigurationSerializer):
    """Serializer para crear configuraciones de sincronización"""
    
    class Meta(SyncConfigurationSerializer.Meta):
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'last_sync_at',
            'last_sync_status', 'total_syncs', 'successful_syncs',
            'success_rate', 'is_due_for_sync', 'created_by_name',
            'django_event_id', 'django_organizer_id', 'django_form_id'
        ]


class SyncExecutionSerializer(serializers.ModelSerializer):
    """Serializer para ejecuciones de sincronización"""
    
    configuration_name = serializers.CharField(source='configuration.name', read_only=True)
    triggered_by_name = serializers.CharField(source='triggered_by.get_full_name', read_only=True)
    duration_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = SyncExecution
        fields = [
            'id', 'configuration', 'configuration_name', 'status', 'trigger',
            'started_at', 'finished_at', 'duration_seconds', 'duration_formatted',
            'orders_processed', 'tickets_processed', 'orders_created',
            'orders_updated', 'tickets_created', 'tickets_updated',
            'error_message', 'celery_task_id', 'triggered_by_name'
        ]
        read_only_fields = [
            'id', 'configuration_name', 'duration_formatted',
            'triggered_by_name'
        ]
    
    def get_duration_formatted(self, obj):
        """Formatear duración de forma legible"""
        if not obj.duration_seconds:
            return None
        
        seconds = obj.duration_seconds
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds}s"
        else:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            return f"{hours}h {remaining_minutes}m"


class SyncCredentialsSerializer(serializers.ModelSerializer):
    """Serializer para credenciales de sincronización"""
    
    class Meta:
        model = SyncCredentials
        fields = [
            'id', 'name', 'ssh_host', 'ssh_port', 'ssh_username',
            'mysql_host', 'mysql_port', 'mysql_database', 'mysql_username',
            'is_active', 'is_default', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SyncTriggerSerializer(serializers.Serializer):
    """Serializer para disparar sincronizaciones manualmente"""
    
    sync_config_id = serializers.UUIDField()
    trigger = serializers.ChoiceField(
        choices=['manual', 'api'],
        default='manual'
    )
    
    def validate_sync_config_id(self, value):
        """Validar que la configuración existe y está activa"""
        try:
            config = SyncConfiguration.objects.get(id=value)
            if config.status not in ['active', 'paused']:
                raise serializers.ValidationError(
                    "La configuración debe estar activa o pausada"
                )
            return value
        except SyncConfiguration.DoesNotExist:
            raise serializers.ValidationError(
                "Configuración de sincronización no encontrada"
            )


class SyncStatsSerializer(serializers.Serializer):
    """Serializer para estadísticas de sincronización"""
    
    total_configurations = serializers.IntegerField()
    active_configurations = serializers.IntegerField()
    paused_configurations = serializers.IntegerField()
    disabled_configurations = serializers.IntegerField()
    error_configurations = serializers.IntegerField()
    
    total_executions_today = serializers.IntegerField()
    successful_executions_today = serializers.IntegerField()
    failed_executions_today = serializers.IntegerField()
    
    total_executions_week = serializers.IntegerField()
    successful_executions_week = serializers.IntegerField()
    failed_executions_week = serializers.IntegerField()
    
    average_success_rate = serializers.FloatField()
    configurations_due_for_sync = serializers.IntegerField()


class SyncTestConnectionSerializer(serializers.Serializer):
    """Serializer para probar conexión con WooCommerce"""
    
    credentials_id = serializers.IntegerField(required=False)
    
    def validate_credentials_id(self, value):
        """Validar que las credenciales existen"""
        if value:
            try:
                SyncCredentials.objects.get(id=value, is_active=True)
                return value
            except SyncCredentials.DoesNotExist:
                raise serializers.ValidationError(
                    "Credenciales no encontradas o inactivas"
                )
        return value
