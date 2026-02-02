"""
🚀 ENTERPRISE MIGRATION SERIALIZERS

Serializers para:
- API de migración (MigrationJob, Log, Checkpoint, etc.)
- Export/Import optimizado con FKs planos y M2M separados
"""

from rest_framework import serializers
from django.db import models as django_models

from .models import (
    MigrationJob, 
    MigrationLog, 
    MigrationCheckpoint,
    MigrationToken,
    BackupJob
)


# =============================================================================
# API SERIALIZERS - Para las vistas de la API
# =============================================================================

class MigrationJobSerializer(serializers.ModelSerializer):
    """Serializer para MigrationJob."""
    
    direction_display = serializers.CharField(source='get_direction_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    executed_by_email = serializers.EmailField(source='executed_by.email', read_only=True, allow_null=True)
    
    class Meta:
        model = MigrationJob
        fields = [
            'id', 'direction', 'direction_display', 'status', 'status_display',
            'source_url', 'target_url', 'progress_percent', 'current_step',
            'export_file_path', 'export_file_size_mb', 'storage_backend',
            'total_models', 'models_completed', 'total_records', 'records_processed',
            'total_files', 'files_transferred',
            'started_at', 'completed_at', 'duration_seconds',
            'error_message', 'executed_by_email', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'progress_percent', 'current_step',
            'export_file_path', 'export_file_size_mb', 'storage_backend',
            'models_completed', 'records_processed', 'files_transferred',
            'started_at', 'completed_at', 'duration_seconds',
            'error_message', 'created_at', 'updated_at'
        ]


class MigrationLogSerializer(serializers.ModelSerializer):
    """Serializer para MigrationLog."""
    
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    
    class Meta:
        model = MigrationLog
        fields = [
            'id', 'job', 'level', 'level_display', 'message',
            'model_name', 'record_count', 'duration_ms',
            'metadata', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp']


class MigrationCheckpointSerializer(serializers.ModelSerializer):
    """Serializer para MigrationCheckpoint."""
    
    is_expired = serializers.BooleanField(read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True, allow_null=True)
    
    class Meta:
        model = MigrationCheckpoint
        fields = [
            'id', 'name', 'description',
            'snapshot_file_path', 'snapshot_size_mb',
            'total_models', 'total_records', 'total_files',
            'database_version', 'environment',
            'is_valid', 'is_expired', 'used_for_restore', 'restored_at',
            'created_by_email', 'expires_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'snapshot_file_path', 'snapshot_size_mb',
            'total_models', 'total_records', 'total_files',
            'database_version', 'is_expired', 'restored_at',
            'created_at', 'updated_at'
        ]


class MigrationTokenSerializer(serializers.ModelSerializer):
    """Serializer para MigrationToken."""
    
    permissions_display = serializers.CharField(source='get_permissions_display', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = MigrationToken
        fields = [
            'id', 'description', 'permissions', 'permissions_display',
            'allowed_ips', 'allowed_domains',
            'expires_at', 'is_single_use', 'is_valid',
            'usage_count', 'last_used_at',
            'created_at'
        ]
        read_only_fields = [
            'id', 'is_valid', 'usage_count', 'last_used_at', 'created_at'
        ]
        # El token no se devuelve en las respuestas por seguridad
        extra_kwargs = {
            'token': {'write_only': True}
        }


class BackupJobSerializer(serializers.ModelSerializer):
    """Serializer para BackupJob."""
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True, allow_null=True)
    
    class Meta:
        model = BackupJob
        fields = [
            'id', 'backup_file', 'file_size_mb', 'original_filename',
            'status', 'status_display', 'progress_percent', 'current_step',
            'restore_sql', 'restore_media', 'create_backup_before',
            'backup_metadata',
            'sql_records_restored', 'media_files_restored', 'media_size_mb',
            'started_at', 'completed_at', 'duration_seconds',
            'error_message',
            'uploaded_by_email', 'safety_backup_path',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'progress_percent', 'current_step',
            'backup_metadata',
            'sql_records_restored', 'media_files_restored', 'media_size_mb',
            'started_at', 'completed_at', 'duration_seconds',
            'error_message', 'safety_backup_path',
            'created_at', 'updated_at'
        ]


# =============================================================================
# MIGRATION SERIALIZER - Para export/import con FKs planos
# =============================================================================

class MigrationSerializer(serializers.ModelSerializer):
    """
    Serializer base optimizado para migración que exporta:
    - ForeignKeys como IDs planos (strings/ints) en vez de objetos nested
    - Many-to-Many fields separados en metadata _m2m_relations
    - Estructura plana compatible con import directo
    
    Uso:
        serializer = MigrationSerializer.for_model(MyModel)
        data = serializer(instances, many=True).data
    """
    
    def to_representation(self, instance):
        """
        Convierte instancia a diccionario plano para migración.
        
        - ForeignKeys se convierten a IDs (no nested objects)
        - ManyToMany se extraen a metadata separada
        - Todos los otros campos se serializan normalmente
        """
        data = {}
        m2m_data = {}
        
        # Obtener todos los campos del modelo
        for field in instance._meta.get_fields():
            field_name = field.name
            
            # Skip campos reverse que no son propios del modelo
            if field.auto_created and not field.concrete:
                continue
            
            # Skip campos que no tienen valor en la instancia
            if not hasattr(instance, field_name):
                continue
            
            try:
                value = getattr(instance, field_name)
                
                # Manejo de ManyToMany - extraer a metadata separada
                if field.many_to_many:
                    # Obtener lista de IDs
                    m2m_ids = []
                    if hasattr(value, 'all'):
                        m2m_ids = list(value.all().values_list('pk', flat=True))
                    m2m_data[field_name] = m2m_ids
                    # NO incluir en data principal
                    continue
                
                # Manejo de ForeignKey - convertir a ID plano
                elif isinstance(field, django_models.ForeignKey):
                    if value is not None:
                        # Extraer solo el ID
                        if hasattr(value, 'pk'):
                            data[field_name + '_id'] = str(value.pk)
                        else:
                            data[field_name + '_id'] = str(value)
                    else:
                        data[field_name + '_id'] = None
                    continue
                
                # Manejo de OneToOne - similar a ForeignKey
                elif isinstance(field, django_models.OneToOneField):
                    if value is not None:
                        if hasattr(value, 'pk'):
                            data[field_name + '_id'] = str(value.pk)
                        else:
                            data[field_name + '_id'] = str(value)
                    else:
                        data[field_name + '_id'] = None
                    continue
                
                # Campos normales - serializar directamente
                else:
                    # FileField/ImageField - solo guardar path
                    if hasattr(value, 'name') and hasattr(field, 'upload_to'):
                        data[field_name] = value.name if value else None
                    # UUID - convertir a string
                    elif hasattr(value, 'hex'):
                        data[field_name] = str(value)
                    # Datetime - ISO format
                    elif hasattr(value, 'isoformat'):
                        data[field_name] = value.isoformat()
                    # Decimal - convertir a float
                    elif hasattr(value, 'as_tuple'):
                        data[field_name] = float(value)
                    # Otros tipos - directo
                    else:
                        data[field_name] = value
                        
            except Exception as e:
                # Si hay error obteniendo el campo, skip silenciosamente
                # Esto evita que un campo problemático bloquee toda la serialización
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Error serializando campo {field_name}: {e}")
                continue
        
        # Agregar metadata de M2M si existen
        if m2m_data:
            data['_m2m_relations'] = m2m_data
        
        return data
    
    @classmethod
    def for_model(cls, model_class):
        """
        Crea un serializer para un modelo específico.
        
        Args:
            model_class: Django model class
            
        Returns:
            MigrationSerializer class configurada para el modelo
        """
        class DynamicMigrationSerializer(cls):
            class Meta:
                model = model_class
                fields = '__all__'
        
        return DynamicMigrationSerializer


def get_migration_serializer_for_model(model):
    """
    Obtiene un MigrationSerializer apropiado para un modelo.
    
    Esta función es un wrapper que siempre retorna un MigrationSerializer
    optimizado para migración, independientemente de si existe un serializer
    custom en api/v1/.
    
    Args:
        model: Django model class
        
    Returns:
        MigrationSerializer class
    """
    return MigrationSerializer.for_model(model)
