"""
Serializers for migration system.
"""

from rest_framework import serializers
from .models import MigrationJob, MigrationLog, MigrationCheckpoint, MigrationToken, BackupJob


class MigrationJobSerializer(serializers.ModelSerializer):
    """Serializer for MigrationJob."""
    
    executed_by_email = serializers.EmailField(source='executed_by.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    direction_display = serializers.CharField(source='get_direction_display', read_only=True)
    
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
    """Serializer for MigrationLog."""
    
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    
    class Meta:
        model = MigrationLog
        fields = [
            'id', 'job', 'level', 'level_display', 'message',
            'model_name', 'record_count', 'duration_ms', 'metadata', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp']


class MigrationCheckpointSerializer(serializers.ModelSerializer):
    """Serializer for MigrationCheckpoint."""
    
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = MigrationCheckpoint
        fields = [
            'id', 'name', 'description', 'snapshot_file_path', 'snapshot_size_mb',
            'total_models', 'total_records', 'total_files',
            'database_version', 'environment', 'is_valid', 'is_expired',
            'used_for_restore', 'restored_at', 'expires_at',
            'created_by_email', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'is_expired', 'used_for_restore', 'restored_at',
            'created_at', 'updated_at'
        ]


class MigrationTokenSerializer(serializers.ModelSerializer):
    """Serializer for MigrationToken."""
    
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = MigrationToken
        fields = [
            'id', 'token', 'description', 'permissions',
            'allowed_ips', 'allowed_domains', 'expires_at',
            'is_single_use', 'used_at', 'usage_count',
            'last_used_at', 'last_used_ip', 'is_valid',
            'created_by_email', 'created_at'
        ]
        read_only_fields = [
            'id', 'used_at', 'usage_count', 'last_used_at',
            'last_used_ip', 'is_valid', 'created_at'
        ]
        extra_kwargs = {
            'token': {'write_only': True}
        }


class BackupJobSerializer(serializers.ModelSerializer):
    """Serializer for BackupJob (restore desde backup GCP)."""
    
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    backup_file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = BackupJob
        fields = [
            'id', 'backup_file', 'backup_file_url', 'file_size_mb', 'original_filename',
            'status', 'status_display', 'progress_percent', 'current_step',
            'restore_sql', 'restore_media', 'create_backup_before',
            'backup_metadata', 'sql_records_restored', 'media_files_restored', 'media_size_mb',
            'started_at', 'completed_at', 'duration_seconds',
            'error_message', 'uploaded_by_email', 'safety_backup_path',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'file_size_mb', 'status', 'progress_percent', 'current_step',
            'backup_metadata', 'sql_records_restored', 'media_files_restored', 'media_size_mb',
            'started_at', 'completed_at', 'duration_seconds',
            'error_message', 'safety_backup_path', 'created_at', 'updated_at'
        ]
    
    def get_backup_file_url(self, obj):
        """Retorna URL del archivo de backup."""
        if obj.backup_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.backup_file.url)
        return None
