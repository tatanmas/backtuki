"""
Serializers for migration system.
"""

from rest_framework import serializers
from .models import MigrationJob, MigrationLog, MigrationCheckpoint, MigrationToken


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
            'export_file_path', 'export_file_size_mb',
            'total_models', 'models_completed', 'total_records', 'records_processed',
            'total_files', 'files_transferred',
            'started_at', 'completed_at', 'duration_seconds',
            'error_message', 'executed_by_email', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'progress_percent', 'current_step',
            'export_file_path', 'export_file_size_mb',
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
