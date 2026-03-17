"""
🚀 ENTERPRISE MEDIA LIBRARY SERIALIZERS
"""

import logging
from urllib.parse import urlparse

from django.conf import settings
from rest_framework import serializers

logger = logging.getLogger(__name__)
from apps.media.models import MediaAsset, MediaUsage
from apps.organizers.models import Organizer
from django.contrib.contenttypes.models import ContentType


def _build_media_url_for_request(url, request):
    """
    Build absolute media URL for the client. En producción la biblioteca de medios
    debe cargar imágenes desde el dominio público (ej. https://tuki.cl), nunca desde
    localhost o el host interno del contenedor.
    - Si BACKEND_URL está definido, se usa SIEMPRE como base para URLs de medios
      (path relativo o URL con localhost), así las thumbnails cargan en el navegador.
    - Si no hay BACKEND_URL, se usa el host del request (desarrollo local).
    """
    if not url:
        return None
    backend_url = (getattr(settings, "BACKEND_URL", None) or "").rstrip("/")
    # En producción (Dako): usar siempre BACKEND_URL para que la biblioteca reciba URLs públicas
    if backend_url:
        if url.startswith(("http://", "https://")):
            if "localhost" in url or "127.0.0.1" in url:
                parsed = urlparse(url)
                path = parsed.path or ""
                if path:
                    return f"{backend_url}{path}" if path.startswith("/") else f"{backend_url}/{path}"
            return url
        path = url if url.startswith("/") else f"/{url}"
        return f"{backend_url}{path}"
    # Desarrollo local: usar request si está disponible
    if request:
        if url.startswith(("http://", "https://")):
            if "localhost" in url or "127.0.0.1" in url:
                parsed = urlparse(url)
                path = parsed.path or ""
                if path:
                    return request.build_absolute_uri(path)
            return url
        return request.build_absolute_uri(url if url.startswith("/") else f"/{url}")
    return url


class MediaAssetSerializer(serializers.ModelSerializer):
    """Serializer for MediaAsset."""
    
    url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
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
            'thumbnail_url',
            'original_filename',
            'content_type',
            'size_bytes',
            'size_mb',
            'width',
            'height',
            'sha256',
            'tags',
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

    def _normalize_tags(self, value):
        """Normalize tags: strip, remove empty, deduplicate (preserve order)."""
        if not isinstance(value, (list, tuple)):
            return []
        seen = set()
        out = []
        for t in value:
            s = (t if isinstance(t, str) else str(t)).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def validate_tags(self, value):
        return self._normalize_tags(value)
    
    def get_url(self, obj):
        """
        Return public URL using request host when available (igual que destinos/experiencias).
        Así la biblioteca de medios sirve imágenes desde tuki.cl en prod, no desde localhost.
        """
        if not obj.file:
            return None
        raw = obj.file.url
        if not raw:
            return None
        request = self.context.get("request")
        if request:
            return _build_media_url_for_request(raw, request)
        return obj.url

    def get_thumbnail_url(self, obj):
        """Return thumbnail URL for grid display; fallback to full url if no thumbnail."""
        if obj.thumbnail:
            raw = obj.thumbnail.url
            if raw:
                request = self.context.get("request")
                if request:
                    return _build_media_url_for_request(raw, request)
                return raw
        return self.get_url(obj)

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
    
    # Accept tags as list (JSON) or JSON string (from FormData)
    tags = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False,
        default=list,
        allow_empty=True,
    )

    class Meta:
        model = MediaAsset
        fields = [
            'file',
            'scope',
            'organizer',
            'original_filename',
            'content_type',
            'tags',
        ]

    def to_internal_value(self, data):
        """Parse tags from FormData (JSON string) or list."""
        if isinstance(data, dict) and 'tags' in data:
            raw = data['tags']
            if isinstance(raw, str):
                try:
                    import json
                    data = {**data, 'tags': json.loads(raw) if raw.strip() else []}
                except (ValueError, TypeError):
                    data = {**data, 'tags': []}
        return super().to_internal_value(data)

    def validate_tags(self, value):
        """Normalize tags for create."""
        if not isinstance(value, (list, tuple)):
            return []
        seen = set()
        out = []
        for t in value:
            s = (t if isinstance(t, str) else str(t)).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def validate_file(self, value):
        """Validate file size and type. Accept by extension or by image/* Content-Type."""
        max_size = MediaAsset.MAX_FILE_SIZE_MB * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError({
                "file": [f"File size exceeds {MediaAsset.MAX_FILE_SIZE_MB}MB limit"]
            })
        if value.size <= 0:
            raise serializers.ValidationError({"file": ["El archivo está vacío (0 bytes)."]})

        allowed_extensions = ('jpg', 'jpeg', 'png', 'webp', 'gif')
        name = getattr(value, 'name', '') or ''
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        content_type = (value.content_type or '').strip().lower()

        # AVIF no soportado (Pillow no lo abre; provoca 400)
        if ext == 'avif' or content_type == 'image/avif':
            raise serializers.ValidationError({
                "file": ["AVIF no está soportado. Use PNG, JPG, WEBP o GIF."]
            })
        # Accept if extension is allowed (browsers often send application/octet-stream)
        if ext in allowed_extensions:
            return value
        # Accept if Content-Type is in our list
        if content_type and content_type in MediaAsset.ALLOWED_CONTENT_TYPES:
            return value
        # Aceptar otros image/* (HEIC → se convierte a jpg en perform_create)
        if content_type and content_type.startswith('image/'):
            return value

        logger.warning(
            "MEDIA upload 400: file name=%r content_type=%r size=%s",
            name or '(no name)',
            content_type or '(none)',
            value.size,
        )
        raise serializers.ValidationError({
            "file": [
                f"File type not allowed (got {content_type or 'unknown'}, extension .{ext or 'none'}). "
                f"Allowed: {', '.join(allowed_extensions)}"
            ]
        })
    
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
        """Return asset URL (usa request host como MediaAssetSerializer)."""
        if not obj.asset or not obj.asset.file:
            return None
        raw = obj.asset.file.url
        if not raw:
            return None
        request = self.context.get("request")
        if request:
            return _build_media_url_for_request(raw, request)
        return obj.asset.url
    
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
            elif hasattr(obj.content_object, 'slot_key'):
                return obj.content_object.slot_key
            elif hasattr(obj.content_object, 'slide_id'):
                return obj.content_object.slide_id
        return None

