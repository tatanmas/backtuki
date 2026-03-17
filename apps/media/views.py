"""
🚀 ENTERPRISE MEDIA LIBRARY VIEWS
REST API for media asset management.
"""

import hashlib
import logging
import operator
from functools import reduce

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
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
    
    def _get_base_queryset(self):
        """
        Apply permission and scope filters only (no q, tags, dates, used).
        Used by get_queryset and by list_tags action.
        """
        queryset = self.queryset.all()
        user = self.request.user
        show_deleted = self.request.query_params.get('show_deleted', 'false').lower() == 'true'
        if not show_deleted:
            queryset = queryset.filter(deleted_at__isnull=True)
        is_superuser = user.is_superuser
        organizer = self.get_organizer()
        if organizer:
            if is_superuser:
                scope = self.request.query_params.get('scope')
                organizer_id = self.request.query_params.get('organizer_id')
                if scope == 'global':
                    queryset = queryset.filter(scope='global')
                elif organizer_id and organizer_id != str(organizer.id):
                    queryset = queryset.filter(organizer_id=organizer_id)
                else:
                    queryset = queryset.filter(scope='organizer', organizer=organizer)
            else:
                queryset = queryset.filter(scope='organizer', organizer=organizer)
        elif is_superuser:
            scope = self.request.query_params.get('scope')
            if scope:
                queryset = queryset.filter(scope=scope)
            organizer_id = self.request.query_params.get('organizer_id')
            if organizer_id:
                queryset = queryset.filter(organizer_id=organizer_id)
        else:
            queryset = queryset.none()
        return queryset

    def get_queryset(self):
        """
        Filter assets based on permissions and query params.
        
        🚀 ENTERPRISE: Organizers see only their own assets; superadmin sees all.
        """
        queryset = self._get_base_queryset()
        q = self.request.query_params.get('q')
        if q:
            queryset = queryset.filter(original_filename__icontains=q)
        created_from = self.request.query_params.get('created_from')
        if created_from:
            queryset = queryset.filter(created_at__gte=created_from)
        created_to = self.request.query_params.get('created_to')
        if created_to:
            queryset = queryset.filter(created_at__lte=created_to)
        used = self.request.query_params.get('used')
        if used == 'true':
            queryset = queryset.annotate(
                usage_count=Count('usages', filter=Q(usages__deleted_at__isnull=True))
            ).filter(usage_count__gt=0)
        elif used == 'false':
            queryset = queryset.annotate(
                usage_count=Count('usages', filter=Q(usages__deleted_at__isnull=True))
            ).filter(usage_count=0)
        tags_param = self.request.query_params.get('tags')
        if tags_param:
            tag_list = [t.strip() for t in tags_param.split(',') if t.strip()]
            if tag_list:
                tag_conditions = [Q(tags__contains=[t]) for t in tag_list]
                queryset = queryset.filter(reduce(operator.or_, tag_conditions))
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
        
        # Save asset (tags from validated_data if present)
        tags = serializer.validated_data.get('tags') or []
        asset = serializer.save(
            uploaded_by=user,
            organizer=organizer if scope == 'organizer' else None,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256_hash,
            tags=tags,
        )
        # Generate thumbnail for fast grid loading (~10-30KB vs full image)
        asset.generate_thumbnail()
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

            # Delete file and thumbnail from storage
            try:
                if asset.file:
                    default_storage.delete(asset.file.name)
                    logger.info(f"🗑️ [MEDIA] Deleted file: {asset.file.name}")
                if asset.thumbnail:
                    default_storage.delete(asset.thumbnail.name)
                    logger.info(f"🗑️ [MEDIA] Deleted thumbnail: {asset.thumbnail.name}")
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

    @action(detail=False, methods=['get'], url_path='tags')
    def list_tags(self, request):
        """
        Return unique tag strings from assets the user can see (same scope/organizer as list).
        For autocomplete / suggestions in TagMultiSelect.
        """
        queryset = self._get_base_queryset()
        limit = 200
        tags_rows = queryset.values_list('tags', flat=True)[:5000]
        seen = set()
        result = []
        for row in tags_rows:
            if not isinstance(row, list):
                continue
            for t in row:
                s = (t if isinstance(t, str) else str(t)).strip()
                if s and s not in seen:
                    seen.add(s)
                    result.append(s)
                    if len(result) >= limit:
                        break
            if len(result) >= limit:
                break
        result.sort(key=str.lower)
        return Response({'tags': result})

    @action(detail=False, methods=['post'], url_path='bulk-update-tags')
    def bulk_update_tags(self, request):
        """
        Add and/or remove tags from multiple assets.
        Body: { "asset_ids": ["uuid", ...], "add_tags": ["tag1"], "remove_tags": ["tag2"] }
        Same permission as PATCH: user must have access to each asset.
        """
        asset_ids = request.data.get('asset_ids') or []
        add_tags = request.data.get('add_tags') or []
        remove_tags = request.data.get('remove_tags') or []
        if not isinstance(asset_ids, list):
            return Response(
                {'error': 'asset_ids must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not asset_ids:
            return Response(
                {'updated': 0, 'message': 'No assets specified'},
                status=status.HTTP_200_OK
            )
        add_set = {str(t).strip() for t in add_tags if str(t).strip()}
        remove_set = {str(t).strip() for t in remove_tags if str(t).strip()}
        if not add_set and not remove_set:
            return Response(
                {'updated': 0, 'message': 'No add_tags or remove_tags provided'},
                status=status.HTTP_200_OK
            )
        base_qs = self._get_base_queryset()
        assets = list(base_qs.filter(id__in=asset_ids))
        if len(assets) != len(asset_ids):
            allowed_ids = {str(a.id) for a in assets}
            requested_ids = set(str(i) for i in asset_ids)
            if requested_ids - allowed_ids:
                return Response(
                    {'error': 'Permission denied for one or more assets'},
                    status=status.HTTP_403_FORBIDDEN
                )
        updated = 0
        for asset in assets:
            tags = list(asset.tags) if isinstance(asset.tags, list) else []
            changed = False
            for r in remove_set:
                if r in tags:
                    tags.remove(r)
                    changed = True
            for a in add_set:
                if a not in tags:
                    tags.append(a)
                    changed = True
            if changed:
                asset.tags = tags
                asset.save(update_fields=['tags'])
                updated += 1
        logger.info(
            "MEDIA bulk_update_tags: %s assets updated (add=%s remove=%s)",
            updated, len(add_set), len(remove_set)
        )
        return Response({
            'updated': updated,
            'message': f'{updated} imagen(es) actualizada(s)',
        }, status=status.HTTP_200_OK)

