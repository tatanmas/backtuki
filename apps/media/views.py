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

from api.v1.pagination import LargePageSizePagination
from django.db.models import Q, Count
from django.core.files.storage import default_storage

from apps.media.models import MediaAsset, MediaUsage


def _unlink_asset_from_accommodations_and_destinations(asset_id):
    """
    Remove references to this media asset from accommodations and landing destinations
    so that after hard-delete no stale IDs remain.
    """
    asset_id_str = str(asset_id)
    from apps.accommodations.models import Accommodation
    from apps.landing_destinations.models import LandingDestination

    # Accommodations: find by gallery_media_ids (JSON contains)
    acc_ids_by_ids = set(
        Accommodation.objects.filter(
            gallery_media_ids__contains=[asset_id_str], deleted_at__isnull=True
        ).values_list("id", flat=True)
    )
    # Fallback: if JSON __contains didn't match (e.g. format), find by scanning gallery_items
    if not acc_ids_by_ids:
        for acc in Accommodation.objects.filter(
            deleted_at__isnull=True
        ).exclude(gallery_items=[]).exclude(gallery_items=None)[:2000]:
            if not acc.gallery_items:
                continue
            if any(str(it.get("media_id")) == asset_id_str for it in acc.gallery_items):
                acc_ids_by_ids.add(acc.id)

    for acc in Accommodation.objects.filter(id__in=acc_ids_by_ids):
        if acc.gallery_media_ids:
            acc.gallery_media_ids = [mid for mid in acc.gallery_media_ids if str(mid) != asset_id_str]
        if acc.gallery_items:
            acc.gallery_items = [it for it in acc.gallery_items if str(it.get("media_id")) != asset_id_str]
        acc.save(update_fields=["gallery_media_ids", "gallery_items"])
        logger.info(
            "MEDIA unlink: removed asset %s from accommodation %s (gallery now %s items)",
            asset_id_str[:8],
            acc.id,
            len(acc.gallery_media_ids),
        )

    # Landing destinations: clear hero or remove from gallery
    for dest in LandingDestination.objects.filter(
        Q(hero_media_id=asset_id) | Q(gallery_media_ids__contains=[asset_id_str])
    ):
        updated = False
        if dest.hero_media_id and str(dest.hero_media_id) == asset_id_str:
            dest.hero_media_id = None
            updated = True
        if dest.gallery_media_ids:
            new_ids = [mid for mid in dest.gallery_media_ids if str(mid) != asset_id_str]
            if len(new_ids) != len(dest.gallery_media_ids):
                dest.gallery_media_ids = new_ids
                updated = True
        if updated:
            dest.save(update_fields=["hero_media_id", "gallery_media_ids"])
from apps.media.serializers import (
    MediaAssetSerializer,
    MediaAssetCreateSerializer,
    MediaUsageSerializer
)
from apps.organizers.models import OrganizerUser

logger = logging.getLogger(__name__)

# Fallback filename when request has no name (e.g. pasted image)
# AVIF no incluido: Pillow no lo soporta y provoca 400 al validar
_ct_to_filename = {
    'image/jpeg': 'image.jpg',
    'image/png': 'image.png',
    'image/webp': 'image.webp',
    'image/gif': 'image.gif',
    'image/heic': 'image.jpg',
    'image/x-heic': 'image.jpg',
}
ALLOWED_EXTENSIONS = ('jpg', 'jpeg', 'png', 'webp', 'gif')


class MediaAssetViewSet(viewsets.ModelViewSet):
    """
    ViewSet for MediaAsset.
    
    🚀 ENTERPRISE FEATURES:
    - Multi-scope filtering (organizer/global)
    - Search by filename
    - Usage tracking
    - Soft delete with usage validation
    - Superadmin cross-organizer access
    - Large page_size for pickers (page_size query param, max 5000)
    """
    
    queryset = MediaAsset.objects.all()
    serializer_class = MediaAssetSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    pagination_class = LargePageSizePagination
    
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
        """Log 400 causes: missing file or validation. Respuesta clara si no llega archivo."""
        file_name = getattr(request.FILES.get('file'), 'name', None) if request.FILES else None
        file_size = getattr(request.FILES.get('file'), 'size', None) if request.FILES else None
        logger.info(
            "MEDIA upload POST | content_type=%s has_files=%s file_name=%s file_size=%s",
            (request.content_type or '')[:50],
            bool(request.FILES),
            file_name,
            file_size,
        )
        if request.content_type and 'multipart' not in request.content_type.lower():
            logger.warning(
                "MEDIA upload 400: Content-Type is %s (expected multipart/form-data)",
                request.content_type,
            )
            return Response(
                {"file": ["Use multipart/form-data y envíe un campo 'file' con la imagen."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not request.FILES:
            logger.warning("MEDIA upload 400: request.FILES is empty (no file in request)")
            return Response(
                {"file": ["No se recibió ningún archivo. Envíe el formulario con encoding multipart/form-data y un campo 'file'."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if 'file' not in request.FILES:
            logger.warning(
                "MEDIA upload 400: 'file' not in FILES, keys=%s",
                list(request.FILES.keys()),
            )
            return Response(
                {"file": ["Falta el campo 'file'. Envíe la imagen en un campo llamado 'file'."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        file_obj = request.FILES['file']
        if file_obj.size == 0:
            logger.warning("MEDIA upload 400: file size is 0, name=%s", getattr(file_obj, 'name', ''))
            return Response(
                {"file": ["El archivo está vacío (0 bytes). Use una imagen con contenido."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return super().create(request, *args, **kwargs)
        except ValidationError as e:
            detail_str = str(e.detail) if e.detail is not None else str(e)
            logger.warning(
                "MEDIA upload 400 validation | detail=%s | file name=%s size=%s",
                detail_str,
                getattr(request.FILES.get('file'), 'name', ''),
                getattr(request.FILES.get('file'), 'size', '?'),
            )
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

        # Asegurar que el nombre del archivo tenga extensión permitida (FileExtensionValidator del modelo)
        ext = (file_obj.name or '').split('.')[-1].lower() if (file_obj.name or '').strip() else ''
        if ext not in ALLOWED_EXTENSIONS:
            safe_stored_name = original_filename if '.' in (original_filename or '') else _ct_to_filename.get(_ct, 'image.jpg')
            file_obj.name = safe_stored_name
        
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
                logger.warning(
                    "MEDIA hard delete blocked: asset %s has %s active usage(s)",
                    asset.id,
                    active_usages,
                )
                return Response(
                    {
                        'error': (
                            f'No se puede eliminar: la imagen tiene {active_usages} uso(s) activo(s). '
                            'Desvincula primero en eventos/experiencias o usa borrado suave.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Unlink from accommodations and destinations so no stale references remain
            _unlink_asset_from_accommodations_and_destinations(asset.id)

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

