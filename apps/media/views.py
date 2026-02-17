"""
🚀 ENTERPRISE MEDIA LIBRARY VIEWS
REST API for media asset management.
"""

import hashlib
import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError
from django.db.models import Q, Count
from django.core.files.storage import default_storage

from apps.media.models import MediaAsset, MediaUsage
from apps.media.serializers import (
    MediaAssetSerializer,
    MediaAssetCreateSerializer,
    MediaUsageSerializer
)
from apps.organizers.models import OrganizerUser

logger = logging.getLogger(__name__)

# Fallback filename when request has no name (e.g. pasted image)
_ct_to_filename = {
    'image/jpeg': 'image.jpg',
    'image/png': 'image.png',
    'image/webp': 'image.webp',
    'image/gif': 'image.gif',
    'image/avif': 'image.avif',
}


class MediaAssetViewSet(viewsets.ModelViewSet):
    """
    ViewSet for MediaAsset.
    
    🚀 ENTERPRISE FEATURES:
    - Multi-scope filtering (organizer/global)
    - Search by filename
    - Usage tracking
    - Soft delete with usage validation
    - Superadmin cross-organizer access
    """
    
    queryset = MediaAsset.objects.all()
    serializer_class = MediaAssetSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def get_organizer(self):
        """Get organizer associated with current user."""
        try:
            if not self.request.user.is_authenticated:
                return None
            
            organizer_users = OrganizerUser.objects.filter(user=self.request.user)
            if organizer_users.exists():
                organizer_user = organizer_users.order_by('-created_at').first()
                return organizer_user.organizer
            return None
        except Exception as e:
            logger.error(f"Error getting organizer: {e}")
            return None
    
    def get_queryset(self):
        """
        Filter assets based on permissions and query params.
        
        🚀 ENTERPRISE: Organizers see only their own assets; superadmin sees all.
        
        SECURITY: Always filter by organizer for non-superadmin users, even if they have staff permissions.
        """
        queryset = self.queryset.all()
        user = self.request.user
        
        # Filter by deleted status first
        show_deleted = self.request.query_params.get('show_deleted', 'false').lower() == 'true'
        if not show_deleted:
            queryset = queryset.filter(deleted_at__isnull=True)
        
        # Check if user is superadmin (must be explicitly superuser, not just staff)
        # Staff users who are organizers should still be filtered by organizer
        is_superuser = user.is_superuser
        
        # Get organizer for the user
        organizer = self.get_organizer()
        
        # Log for debugging security
        logger.debug(
            f"🔒 [MEDIA] Access check - User: {user.id}, "
            f"is_superuser: {is_superuser}, is_staff: {user.is_staff}, "
            f"organizer: {organizer.id if organizer else None}"
        )
        
        # CRITICAL SECURITY: If user has an organizer, they MUST only see their organizer's assets
        # Even if they have staff permissions, if they're linked to an organizer, filter by it
        if organizer:
            # User is linked to an organizer - they can ONLY see their organizer's assets
            # unless they are explicitly superuser AND requesting with specific params
            if is_superuser:
                # Superuser with organizer: check if they're requesting specific scope/organizer
                # If no specific params, default to their organizer for security
                scope = self.request.query_params.get('scope')
                organizer_id = self.request.query_params.get('organizer_id')
                
                # If requesting global scope or different organizer, allow it (superuser privilege)
                if scope == 'global':
                    queryset = queryset.filter(scope='global')
                elif organizer_id and organizer_id != str(organizer.id):
                    # Requesting different organizer - superuser can do this
                    queryset = queryset.filter(organizer_id=organizer_id)
                else:
                    # No specific params or requesting own organizer - default to their organizer
                    queryset = queryset.filter(
                        scope='organizer',
                        organizer=organizer
                    )
            else:
                # Regular organizer user: STRICTLY filter by their organizer
                queryset = queryset.filter(
                    scope='organizer',
                    organizer=organizer
                )
        elif is_superuser:
            # Superuser without organizer link: can see all (filter by params if provided)
            scope = self.request.query_params.get('scope')
            if scope:
                queryset = queryset.filter(scope=scope)
            
            organizer_id = self.request.query_params.get('organizer_id')
            if organizer_id:
                queryset = queryset.filter(organizer_id=organizer_id)
        else:
            # User has no organizer and is not superadmin: return empty
            queryset = queryset.none()
        
        # Search by filename
        q = self.request.query_params.get('q')
        if q:
            queryset = queryset.filter(original_filename__icontains=q)
        
        # Filter by date range
        created_from = self.request.query_params.get('created_from')
        if created_from:
            queryset = queryset.filter(created_at__gte=created_from)
        
        created_to = self.request.query_params.get('created_to')
        if created_to:
            queryset = queryset.filter(created_at__lte=created_to)
        
        # Filter by usage
        used = self.request.query_params.get('used')
        if used == 'true':
            queryset = queryset.annotate(
                usage_count=Count('usages', filter=Q(usages__deleted_at__isnull=True))
            ).filter(usage_count__gt=0)
        elif used == 'false':
            queryset = queryset.annotate(
                usage_count=Count('usages', filter=Q(usages__deleted_at__isnull=True))
            ).filter(usage_count=0)
        
        return queryset
    
    def get_serializer_class(self):
        """Use create serializer for POST."""
        if self.action == 'create':
            return MediaAssetCreateSerializer
        return MediaAssetSerializer

    def create(self, request, *args, **kwargs):
        """Log 400 causes: missing file or validation."""
        if request.content_type and 'multipart' not in request.content_type.lower():
            logger.warning(
                "MEDIA upload 400: Content-Type is %s (expected multipart/form-data)",
                request.content_type,
            )
        if not request.FILES:
            logger.warning("MEDIA upload 400: request.FILES is empty (no file in request)")
        elif 'file' not in request.FILES:
            logger.warning(
                "MEDIA upload 400: 'file' not in FILES, keys=%s",
                list(request.FILES.keys()),
            )
        try:
            return super().create(request, *args, **kwargs)
        except ValidationError as e:
            logger.warning("MEDIA upload 400 validation: %s", e.detail)
            raise

    def perform_create(self, serializer):
        """
        Create media asset with automatic metadata extraction.
        
        🚀 ENTERPRISE: Auto-assign organizer, extract metadata, compute hash.
        """
        user = self.request.user
        is_superadmin = user.is_staff or user.is_superuser
        
        # Determine scope and organizer
        scope = serializer.validated_data.get('scope', 'organizer')
        organizer = serializer.validated_data.get('organizer')
        
        # If not provided, auto-assign organizer for non-superadmin
        if scope == 'organizer' and not organizer:
            organizer = self.get_organizer()
            if not organizer:
                if is_superadmin:
                    # Superadmin without organizer link: allow as global asset
                    scope = 'global'
                    serializer.validated_data['scope'] = 'global'
                else:
                    from rest_framework.exceptions import PermissionDenied
                    logger.warning(
                        "MEDIA upload 403: user %s has no organizer (organizer scope)",
                        user.id,
                    )
                    raise PermissionDenied(
                        "No organizer associated with your account. You must be linked to an organizer to upload to the media library."
                    )
        
        # Extract file metadata
        file_obj = serializer.validated_data['file']
        # Use provided values or extract from file; fallback so we never save empty filename
        _name = (serializer.validated_data.get('original_filename') or file_obj.name or '').strip()
        _ct = (serializer.validated_data.get('content_type') or file_obj.content_type or '').strip().lower()
        if not _name:
            _name = _ct_to_filename.get(_ct, 'image.jpg')
        original_filename = _name
        content_type = _ct or 'image/jpeg'
        size_bytes = file_obj.size
        
        # Compute SHA256 hash for deduplication
        file_obj.seek(0)
        sha256_hash = hashlib.sha256(file_obj.read()).hexdigest()
        file_obj.seek(0)
        
        # Set organizer in serializer data BEFORE save so upload_to path is correct
        if scope == 'organizer' and organizer:
            serializer.validated_data['organizer'] = organizer
        
        # Save asset
        asset = serializer.save(
            uploaded_by=user,
            organizer=organizer if scope == 'organizer' else None,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256_hash
        )
        
        logger.info(
            f"📸 [MEDIA] Asset created: {asset.id} by user {user.id} "
            f"(scope={scope}, organizer={organizer.id if organizer else None})"
        )
    
    def destroy(self, request, *args, **kwargs):
        """
        Soft delete by default; hard delete for superadmin with ?hard=true.
        
        🚀 ENTERPRISE: Block hard delete if asset has active usages (organizer).
        """
        asset = self.get_object()
        hard_delete = request.query_params.get('hard', 'false').lower() == 'true'
        is_superadmin = request.user.is_staff or request.user.is_superuser
        
        if hard_delete:
            # Hard delete: only superadmin, and check usages
            if not is_superadmin:
                return Response(
                    {'error': 'Only superadmin can hard delete assets'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check usages
            active_usages = asset.usages.filter(deleted_at__isnull=True).count()
            if active_usages > 0:
                return Response(
                    {
                        'error': f'Asset has {active_usages} active usage(s). '
                                 'Soft delete recommended or unlink first.'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Delete file from storage
            try:
                if asset.file:
                    default_storage.delete(asset.file.name)
                    logger.info(f"🗑️ [MEDIA] Deleted file: {asset.file.name}")
            except Exception as e:
                logger.warning(f"⚠️ [MEDIA] Could not delete file {asset.file.name}: {e}")
            
            # Hard delete
            asset.delete()
            logger.info(f"🗑️ [MEDIA] Hard deleted asset: {kwargs.get('pk')}")
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            # Soft delete
            asset.soft_delete()
            logger.info(f"🗑️ [MEDIA] Soft deleted asset: {asset.id}")
            return Response(
                {'message': 'Asset soft deleted successfully'},
                status=status.HTTP_200_OK
            )
    
    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        """
        Restore a soft-deleted asset.
        
        🚀 ENTERPRISE: Only superadmin or asset owner.
        """
        asset = self.get_object()
        
        if not asset.is_deleted:
            return Response(
                {'error': 'Asset is not deleted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check permissions
        organizer = self.get_organizer()
        is_superadmin = request.user.is_staff or request.user.is_superuser
        
        if not is_superadmin:
            if asset.scope == 'organizer' and asset.organizer != organizer:
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
            elif asset.scope == 'global':
                return Response(
                    {'error': 'Only superadmin can restore global assets'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        asset.restore()
        logger.info(f"♻️ [MEDIA] Restored asset: {asset.id}")
        
        return Response(
            MediaAssetSerializer(asset, context={'request': request}).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['get'], url_path='usages')
    def usages(self, request, pk=None):
        """
        Get all usages of an asset.
        
        🚀 ENTERPRISE: Shows where asset is used (Event, Experience, etc.).
        
        SECURITY: Superadmin can see all usages; organizers only see usages of their assets.
        """
        asset = self.get_object()
        
        # Check permissions: superadmin can see all, organizers only their own
        is_superuser = request.user.is_superuser
        organizer = self.get_organizer()
        
        if not is_superuser:
            # Regular organizer: can only see usages of their own assets
            if asset.scope == 'organizer' and asset.organizer != organizer:
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
            elif asset.scope == 'global':
                # Organizers cannot see usages of global assets
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        usages = asset.usages.filter(deleted_at__isnull=True)
        
        serializer = MediaUsageSerializer(usages, many=True, context={'request': request})
        
        return Response({
            'asset_id': str(asset.id),
            'usage_count': usages.count(),
            'usages': serializer.data
        })

