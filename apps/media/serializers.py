"""
🚀 ENTERPRISE MEDIA LIBRARY SERIALIZERS
"""

from rest_framework import serializers
from apps.media.models import MediaAsset, MediaUsage
from apps.organizers.models import Organizer
from django.contrib.contenttypes.models import ContentType


class MediaAssetSerializer(serializers.ModelSerializer):
    """Serializer for MediaAsset."""
    
    url = serializers.SerializerMethodField()
    size_mb = serializers.SerializerMethodField()
    usage_count = serializers.SerializerMethodField()
    uploaded_by_name = serializers.SerializerMethodField()
    organizer_name = serializers.SerializerMethodField()
    
    class Meta:
        model = MediaAsset
        fields = [
            'id',
            'scope',
            'organizer',
            'organizer_name',
            'uploaded_by',
            'uploaded_by_name',
            'file',
            'url',
            'original_filename',
            'content_type',
            'size_bytes',
            'size_mb',
            'width',
            'height',
            'sha256',
            'usage_count',
            'created_at',
            'deleted_at'
        ]
        read_only_fields = [
            'id',
            'uploaded_by',
            'size_bytes',
            'width',
            'height',
            'sha256',
            'created_at',
            'deleted_at'
        ]
    
    def get_url(self, obj):
        """Return public URL; use request host when available for correct domain."""
        request = self.context.get('request')
        if request and obj.file:
            return request.build_absolute_uri(obj.file.url)
        return obj.url
    
    def get_size_mb(self, obj):
        """Return size in MB."""
        return obj.size_mb
    
    def get_usage_count(self, obj):
        """Return number of usages."""
        return obj.usage_count()
    
    def get_uploaded_by_name(self, obj):
        """Return uploader name."""
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        return None
    
    def get_organizer_name(self, obj):
        """Return organizer name."""
        if obj.organizer:
            return obj.organizer.name
        return None


class MediaAssetCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating MediaAsset."""
    
    # Make these optional - they'll be extracted from file if not provided
    original_filename = serializers.CharField(required=False, allow_blank=True)
    content_type = serializers.CharField(required=False, allow_blank=True)
    # Make organizer optional - perform_create will auto-assign it for organizer scope
    # Use read_only=False but allow_null - queryset will be set dynamically if needed
    organizer = serializers.PrimaryKeyRelatedField(
        required=False, 
        allow_null=True, 
        queryset=Organizer.objects.all()
    )
    
    class Meta:
        model = MediaAsset
        fields = [
            'file',
            'scope',
            'organizer',
            'original_filename',
            'content_type'
        ]
    
    def validate_file(self, value):
        """Validate file size and type."""
        # Check file size
        max_size = MediaAsset.MAX_FILE_SIZE_MB * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size exceeds {MediaAsset.MAX_FILE_SIZE_MB}MB limit"
            )
        
        # Check content type
        content_type = value.content_type
        if content_type not in MediaAsset.ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(
                f"File type {content_type} not allowed. "
                f"Allowed types: {', '.join(MediaAsset.ALLOWED_CONTENT_TYPES)}"
            )
        
        return value
    
    def validate(self, attrs):
        """Validate scope/organizer consistency."""
        scope = attrs.get('scope', 'organizer')
        organizer = attrs.get('organizer')
        
        # Don't require organizer here - perform_create will auto-assign it
        # Only validate that global assets don't have an organizer
        if scope == 'global' and organizer:
            raise serializers.ValidationError({
                'organizer': 'Global assets cannot have an organizer'
            })
        
        return attrs


class MediaUsageSerializer(serializers.ModelSerializer):
    """Serializer for MediaUsage."""
    
    asset_url = serializers.SerializerMethodField()
    asset_filename = serializers.SerializerMethodField()
    owner_type = serializers.SerializerMethodField()
    owner_id = serializers.SerializerMethodField()
    owner_title = serializers.SerializerMethodField()
    
    class Meta:
        model = MediaUsage
        fields = [
            'id',
            'asset',
            'asset_url',
            'asset_filename',
            'owner_type',
            'owner_id',
            'owner_title',
            'field_name',
            'created_at',
            'deleted_at'
        ]
        read_only_fields = ['id', 'created_at', 'deleted_at']
    
    def get_asset_url(self, obj):
        """Return asset URL."""
        return obj.asset.url if obj.asset else None
    
    def get_asset_filename(self, obj):
        """Return asset filename."""
        return obj.asset.original_filename if obj.asset else None
    
    def get_owner_type(self, obj):
        """Return content type model name."""
        return obj.content_type.model if obj.content_type else None
    
    def get_owner_id(self, obj):
        """Return object ID."""
        return str(obj.object_id)
    
    def get_owner_title(self, obj):
        """Return owner title if available."""
        if obj.content_object:
            if hasattr(obj.content_object, 'title'):
                return obj.content_object.title
            elif hasattr(obj.content_object, 'name'):
                return obj.content_object.name
        return None

