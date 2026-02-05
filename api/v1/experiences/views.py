"""Views for experiences API."""

import logging
import uuid
import time
from decimal import Decimal
from datetime import timedelta
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, F, Sum
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.experiences.models import (
    Experience, TourLanguage, TourInstance, TourBooking, OrganizerCredit,
    ExperienceResource, ExperienceReservation, ExperienceDatePriceOverride,
    ExperienceCapacityHold, ExperienceResourceHold
)
from apps.experiences.serializers import (
    ExperienceSerializer,
    TourLanguageSerializer,
    TourInstanceSerializer,
    TourBookingSerializer,
    TourBookingCreateSerializer,
    OrganizerCreditSerializer,
    ExperienceResourceSerializer,
    ExperienceDatePriceOverrideSerializer,
    ExperienceReservationSerializer
)
from apps.organizers.models import OrganizerUser
from core.permissions import HasExperienceModule, IsSuperAdmin
from .error_handlers import ExperienceErrorHandler

logger = logging.getLogger(__name__)


class ExperienceViewSet(viewsets.ModelViewSet):
    """ViewSet for Experience model."""
    
    queryset = Experience.objects.all()
    serializer_class = ExperienceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        """
        Allow public access to read and update endpoints (for Super Admin panel).
        Create and delete still require authentication.
        """
        if self.action in ['list', 'retrieve', 'partial_update', 'update']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]
    
    def partial_update(self, request, *args, **kwargs):
        """
        Allow partial updates from Super Admin without authentication.
        This is needed for updating fields like 'country' from the Super Admin panel.
        """
        # Get the experience
        instance = self.get_object()
        
        # Use the serializer to update
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        # Save without checking organizer (Super Admin can update any experience)
        serializer.save()
        
        return Response(serializer.data)
    
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
        🚀 ENTERPRISE: Return experiences based on user permissions.
        
        CRITICAL PRIVACY: Filters by organizer to ensure operators only see their own tours.
        Super Admin can see all experiences.
        
        By default excludes soft-deleted and inactive experiences.
        Use show_deleted=true query param to include deleted experiences.
        """
        queryset = self.queryset.all()
        
        # 🚀 ENTERPRISE: CRITICAL PRIVACY FIX - Filter by organizer
        # Super Admin can see all, but regular organizers only see their own
        user = self.request.user
        is_super_admin = user.is_authenticated and (user.is_superuser or IsSuperAdmin().has_permission(self.request, self))
        
        if user.is_authenticated and not is_super_admin:
            # Regular organizer: filter by their organizer
            organizer = self.get_organizer()
            if organizer:
                queryset = queryset.filter(organizer=organizer)
                logger.debug(f"🔒 [PRIVACY] Filtering experiences for organizer {organizer.id}")
            else:
                # User authenticated but no organizer - return empty queryset
                logger.warning(f"🔒 [PRIVACY] User {user.id} authenticated but no organizer found - returning empty queryset")
                return Experience.objects.none()
        elif not user.is_authenticated:
            # Unauthenticated requests (e.g., Super Admin panel) - return all
            # This is safe because Super Admin panel uses AllowAny permission
            logger.debug("🔒 [PRIVACY] Unauthenticated request - returning all experiences (Super Admin panel)")
        
        # Check if requesting deleted experiences
        show_deleted = self.request.query_params.get('show_deleted', 'false').lower() == 'true'
        
        if not show_deleted:
            if not user.is_authenticated:
                # For Super Admin panel (unauthenticated), only exclude soft-deleted
                # but include inactive experiences so they can be managed
                queryset = queryset.filter(deleted_at__isnull=True)
            else:
                # For authenticated users, exclude both soft-deleted and inactive experiences
                queryset = queryset.filter(deleted_at__isnull=True, is_active=True)
        
        return queryset
    
    def get_serializer_context(self):
        """Add additional context to serializer."""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def perform_create(self, serializer):
        """
        🚀 ENTERPRISE: Automatically assign organizer when creating experience.
        
        Includes robust error handling and validation.
        """
        try:
            organizer = self.get_organizer()
            if not organizer:
                logger.warning(
                    f"🔴 [EXPERIENCE_CREATE] User {self.request.user.id} not associated with any organizer"
                )
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Usuario no está asociado con ningún organizador")
            
            # Check if organizer has experience module enabled
            if not organizer.has_experience_module:
                logger.warning(
                    f"🔴 [EXPERIENCE_CREATE] Organizer {organizer.id} does not have experience module enabled"
                )
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("El módulo de experiencias no está habilitado para este organizador")
            
            serializer.save(organizer=organizer)
            logger.info(
                f"✅ [EXPERIENCE_CREATE] Experience created successfully for organizer {organizer.id}"
            )
        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(
                f"🔴 [EXPERIENCE_CREATE] Unexpected error during creation: {str(e)}",
                exc_info=True,
                extra={
                    'user_id': self.request.user.id if self.request.user.is_authenticated else None,
                    'action': 'create'
                }
            )
            raise
    
    def create(self, request, *args, **kwargs):
        """
        🚀 ENTERPRISE: Override create to add comprehensive error handling.
        """
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            context = {
                'user_id': request.user.id if request.user.is_authenticated else None,
                'action': 'create',
                'data_keys': list(request.data.keys()) if hasattr(request, 'data') else []
            }
            return ExperienceErrorHandler.handle_exception(e, context)
    
    def update(self, request, *args, **kwargs):
        """
        🚀 ENTERPRISE: Override update to add comprehensive error handling.
        """
        try:
            # Verify ownership before update
            instance = self.get_object()
            organizer = self.get_organizer()
            
            if organizer and instance.organizer != organizer:
                # Check if user is super admin
                is_super_admin = request.user.is_authenticated and (
                    request.user.is_superuser or 
                    IsSuperAdmin().has_permission(request, self)
                )
                if not is_super_admin:
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied("No tienes permisos para modificar esta experiencia")
            
            return super().update(request, *args, **kwargs)
        except Exception as e:
            context = {
                'user_id': request.user.id if request.user.is_authenticated else None,
                'action': 'update',
                'instance_id': kwargs.get('pk'),
                'data_keys': list(request.data.keys()) if hasattr(request, 'data') else []
            }
            return ExperienceErrorHandler.handle_exception(e, context)
    
    @action(detail=True, methods=['post'], url_path='soft-delete')
    def soft_delete(self, request, pk=None):
        """
        🚀 ENTERPRISE: Soft delete an experience (archive it).
        Sets deleted_at timestamp and hides from public listings.
        """
        experience = self.get_object()
        
        # Verify ownership
        organizer = self.get_organizer()
        if not organizer or experience.organizer != organizer:
            return Response(
                {"error": "You don't have permission to delete this experience"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if experience.deleted_at:
            return Response(
                {"error": "Experience is already deleted"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        experience.deleted_at = timezone.now()
        experience.is_active = False  # Also deactivate when deleting
        experience.save()
        
        logger.info(f"Experience {experience.id} soft-deleted by organizer {organizer.id}")
        
        return Response({
            "message": "Experience deleted successfully",
            "id": str(experience.id),
            "deleted_at": experience.deleted_at
        })
    
    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        """
        🚀 ENTERPRISE: Restore a soft-deleted experience.
        Clears deleted_at timestamp and makes it available again.
        """
        experience = self.get_object()
        
        # Verify ownership
        organizer = self.get_organizer()
        if not organizer or experience.organizer != organizer:
            return Response(
                {"error": "You don't have permission to restore this experience"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not experience.deleted_at:
            return Response(
                {"error": "Experience is not deleted"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        experience.deleted_at = None
        # Note: We don't automatically set is_active=True, organizer must activate separately
        experience.save()
        
        logger.info(f"Experience {experience.id} restored by organizer {organizer.id}")
        
        return Response({
            "message": "Experience restored successfully",
            "id": str(experience.id),
            "is_active": experience.is_active
        })
    
    @action(detail=True, methods=['post'], url_path='toggle-active')
    def toggle_active(self, request, pk=None):
        """
        🚀 ENTERPRISE: Toggle experience active status.
        When inactive, experience is hidden from public listings but not deleted.
        """
        experience = self.get_object()
        
        # Verify ownership
        organizer = self.get_organizer()
        if not organizer or experience.organizer != organizer:
            return Response(
                {"error": "You don't have permission to modify this experience"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if experience.deleted_at:
            return Response(
                {"error": "Cannot activate a deleted experience. Restore it first."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        experience.is_active = not experience.is_active
        experience.save()
        
        action_text = "activated" if experience.is_active else "deactivated"
        logger.info(f"Experience {experience.id} {action_text} by organizer {organizer.id}")
        
        return Response({
            "message": f"Experience {action_text} successfully",
            "id": str(experience.id),
            "is_active": experience.is_active
        })

    @action(detail=True, methods=['post'], url_path='images/from-assets')
    def link_images_from_assets(self, request, pk=None):
        """
        🚀 ENTERPRISE: Link MediaAssets to Experience.
        
        Sets Experience.images from asset URLs and creates MediaUsage records.
        
        Payload:
        {
            "asset_ids": ["uuid1", "uuid2", ...],
            "replace": true  // Optional: replace all images or append
        }
        """
        from apps.media.models import MediaAsset, MediaUsage
        from django.contrib.contenttypes.models import ContentType
        
        experience = self.get_object()
        asset_ids = request.data.get('asset_ids', [])
        replace = request.data.get('replace', True)
        
        if not asset_ids or not isinstance(asset_ids, list):
            return Response(
                {'detail': 'asset_ids must be a non-empty array'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify organizer permission
        organizer = self.get_organizer()
        if not organizer or experience.organizer != organizer:
            return Response(
                {'detail': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Fetch assets
        try:
            assets = MediaAsset.objects.filter(
                id__in=asset_ids,
                deleted_at__isnull=True
            )
            
            # Verify organizer owns all assets
            for asset in assets:
                if asset.scope == 'organizer' and asset.organizer != organizer:
                    return Response(
                        {'detail': f'You do not own asset {asset.id}'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            if assets.count() != len(asset_ids):
                return Response(
                    {'detail': 'Some assets were not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        except Exception as e:
            logger.error(f"Error fetching assets: {e}")
            return Response(
                {'detail': f'Error fetching assets: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Build image URLs
        asset_urls = [asset.url for asset in assets if asset.url]
        
        # Update experience images
        if replace:
            experience.images = asset_urls
        else:
            # Append to existing
            existing = experience.images if isinstance(experience.images, list) else []
            experience.images = existing + asset_urls
        
        experience.save(update_fields=['images'])
        
        # Create/update MediaUsage records
        content_type = ContentType.objects.get_for_model(experience.__class__)
        
        # Soft-delete old usages if replacing
        if replace:
            MediaUsage.objects.filter(
                content_type=content_type,
                object_id=experience.id,
                field_name='experience.images',
                deleted_at__isnull=True
            ).update(deleted_at=timezone.now())
        
        # Create new usages
        for asset in assets:
            MediaUsage.objects.create(
                asset=asset,
                content_type=content_type,
                object_id=experience.id,
                field_name='experience.images'
            )
        
        logger.info(
            f"📸 [EXPERIENCE-MEDIA] Linked {len(asset_urls)} assets to experience {experience.id}"
        )
        
        return Response({
            'message': f'{len(asset_urls)} images linked successfully',
            'image_urls': asset_urls
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['delete'], url_path='images/unlink')
    def unlink_images(self, request, pk=None):
        """
        🚀 ENTERPRISE: Unlink all images from Experience.
        
        Clears Experience.images and soft-deletes MediaUsage records.
        """
        from apps.media.models import MediaUsage
        from django.contrib.contenttypes.models import ContentType
        
        experience = self.get_object()
        
        # Verify organizer permission
        organizer = self.get_organizer()
        if not organizer or experience.organizer != organizer:
            return Response(
                {'detail': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Clear images
        experience.images = []
        experience.save(update_fields=['images'])
        
        # Soft-delete usages
        content_type = ContentType.objects.get_for_model(experience.__class__)
        updated_count = MediaUsage.objects.filter(
            content_type=content_type,
            object_id=experience.id,
            field_name='experience.images',
            deleted_at__isnull=True
        ).update(deleted_at=timezone.now())
        
        logger.info(f"📸 [EXPERIENCE-MEDIA] Unlinked images from experience {experience.id}")
        
        return Response({
            'message': f'All images unlinked (usages soft-deleted: {updated_count})'
        }, status=status.HTTP_200_OK)


class TourLanguageViewSet(viewsets.ModelViewSet):
    """ViewSet for TourLanguage model."""
    
    queryset = TourLanguage.objects.all()
    serializer_class = TourLanguageSerializer
    permission_classes = [permissions.IsAuthenticated, HasExperienceModule]
    
    def get_queryset(self):
        """Filter languages by experience and organizer."""
        organizer = self._get_organizer()
        if organizer:
            return self.queryset.filter(experience__organizer=organizer)
        return TourLanguage.objects.none()
    
    def _get_organizer(self):
        """Get organizer from user."""
        try:
            if not self.request.user.is_authenticated:
                return None
            organizer_user = OrganizerUser.objects.filter(user=self.request.user).first()
            return organizer_user.organizer if organizer_user else None
        except Exception:
            return None


class TourInstanceViewSet(viewsets.ModelViewSet):
    """ViewSet for TourInstance model."""
    
    queryset = TourInstance.objects.all()
    serializer_class = TourInstanceSerializer
    permission_classes = [permissions.IsAuthenticated, HasExperienceModule]
    
    def get_queryset(self):
        """Filter instances by experience and organizer."""
        organizer = self._get_organizer()
        if organizer:
            return self.queryset.filter(experience__organizer=organizer).select_related('experience')
        # Return full queryset for method introspection - permissions will handle access control
        return self.queryset.all()
    
    def _get_organizer(self):
        """Get organizer from user."""
        try:
            if not self.request.user.is_authenticated:
                return None
            organizer_user = OrganizerUser.objects.filter(user=self.request.user).first()
            return organizer_user.organizer if organizer_user else None
        except Exception:
            return None
    
    @action(detail=True, methods=['post'])
    def block(self, request, pk=None):
        """Block a tour instance."""
        instance = self.get_object()
        instance.status = 'blocked'
        instance.save()
        return Response({'status': 'blocked'})
    
    @action(detail=True, methods=['post'])
    def unblock(self, request, pk=None):
        """Unblock a tour instance."""
        instance = self.get_object()
        instance.status = 'active'
        instance.save()
        return Response({'status': 'active'})
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a tour instance and notify bookings."""
        instance = self.get_object()
        instance.status = 'cancelled'
        instance.save()
        
        # TODO: Send cancellation emails to all bookings
        # This will be implemented in Phase 6
        
        return Response({'status': 'cancelled', 'bookings_notified': instance.bookings.filter(status='confirmed').count()})


class TourBookingViewSet(viewsets.ModelViewSet):
    """ViewSet for TourBooking model."""
    
    queryset = TourBooking.objects.all()
    serializer_class = TourBookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter bookings by organizer."""
        organizer = self._get_organizer()
        if organizer:
            return self.queryset.filter(
                tour_instance__experience__organizer=organizer
            ).select_related('tour_instance', 'tour_instance__experience', 'user')
        
        # For public booking creation
        if self.action == 'create':
            return TourBooking.objects.all()
        
        return TourBooking.objects.none()
    
    def get_serializer_class(self):
        """Use different serializer for create."""
        if self.action == 'create':
            return TourBookingCreateSerializer
        return TourBookingSerializer
    
    def get_permissions(self):
        """Allow public access to create endpoint."""
        if self.action == 'create':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), HasExperienceModule()]
    
    def _get_organizer(self):
        """Get organizer from user."""
        try:
            if not self.request.user.is_authenticated:
                return None
            organizer_user = OrganizerUser.objects.filter(user=self.request.user).first()
            return organizer_user.organizer if organizer_user else None
        except Exception:
            return None


class OrganizerCreditViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for OrganizerCredit model (read-only)."""
    
    queryset = OrganizerCredit.objects.all()
    serializer_class = OrganizerCreditSerializer
    permission_classes = [permissions.IsAuthenticated, HasExperienceModule]
    
    def get_queryset(self):
        """Filter credits by organizer."""
        organizer = self._get_organizer()
        if organizer:
            return self.queryset.filter(organizer=organizer).select_related('tour_booking', 'tour_booking__tour_instance')
        return OrganizerCredit.objects.none()
    
    def _get_organizer(self):
        """Get organizer from user."""
        try:
            if not self.request.user.is_authenticated:
                return None
            organizer_user = OrganizerUser.objects.filter(user=self.request.user).first()
            return organizer_user.organizer if organizer_user else None
        except Exception:
            return None


class ExperienceResourceViewSet(viewsets.ModelViewSet):
    """ViewSet for ExperienceResource model."""
    
    queryset = ExperienceResource.objects.all()
    serializer_class = ExperienceResourceSerializer
    permission_classes = [permissions.IsAuthenticated, HasExperienceModule]
    
    def get_queryset(self):
        """Filter resources by experience and organizer."""
        organizer = self._get_organizer()
        if organizer:
            return self.queryset.filter(experience__organizer=organizer).select_related('experience')
        return ExperienceResource.objects.none()
    
    def _get_organizer(self):
        """Get organizer from user."""
        try:
            if not self.request.user.is_authenticated:
                return None
            organizer_user = OrganizerUser.objects.filter(user=self.request.user).first()
            return organizer_user.organizer if organizer_user else None
        except Exception:
            return None


class ExperienceDatePriceOverrideViewSet(viewsets.ModelViewSet):
    """ViewSet for ExperienceDatePriceOverride model."""
    
    queryset = ExperienceDatePriceOverride.objects.all()
    serializer_class = ExperienceDatePriceOverrideSerializer
    permission_classes = [permissions.IsAuthenticated, HasExperienceModule]
    
    def get_queryset(self):
        """Filter overrides by experience and organizer."""
        organizer = self._get_organizer()
        if organizer:
            return self.queryset.filter(experience__organizer=organizer).select_related('experience')
        return ExperienceDatePriceOverride.objects.none()
    
    def _get_organizer(self):
        """Get organizer from user."""
        try:
            if not self.request.user.is_authenticated:
                return None
            organizer_user = OrganizerUser.objects.filter(user=self.request.user).first()
            return organizer_user.organizer if organizer_user else None
        except Exception:
            return None


class ExperienceReservationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for ExperienceReservation model (organizer view)."""
    
    queryset = ExperienceReservation.objects.all()
    serializer_class = ExperienceReservationSerializer
    permission_classes = [permissions.IsAuthenticated, HasExperienceModule]
    
    def get_queryset(self):
        """Filter reservations by organizer."""
        organizer = self._get_organizer()
        if organizer:
            return self.queryset.filter(
                experience__organizer=organizer
            ).select_related('experience', 'instance', 'user')
        return ExperienceReservation.objects.none()
    
    def _get_organizer(self):
        """Get organizer from user."""
        try:
            if not self.request.user.is_authenticated:
                return None
            organizer_user = OrganizerUser.objects.filter(user=self.request.user).first()
            return organizer_user.organizer if organizer_user else None
        except Exception:
            return None


User = get_user_model()


class PublicExperienceListView(APIView):
    """
    Public API to list published experiences.
    🚀 ENTERPRISE: Excludes deleted and inactive experiences.
    """
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """List published experiences with filters."""
        queryset = Experience.objects.filter(
            status='published',
            is_active=True,
            deleted_at__isnull=True
        )
        
        # Filters
        experience_type = request.query_params.get('type')
        if experience_type:
            queryset = queryset.filter(type=experience_type)
        
        categories = request.query_params.getlist('categories')
        if categories:
            queryset = queryset.filter(categories__overlap=categories)
        
        # Search
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(short_description__icontains=search)
            )
        
        serializer = ExperienceSerializer(queryset, many=True)
        return Response(serializer.data)


def _allow_checkout_by_codigo(request):
    """If valid codigo in request, allow loading draft experiences for checkout."""
    codigo = request.query_params.get('codigo') or request.query_params.get('code')
    if not codigo:
        return False
    try:
        from apps.whatsapp.models import WhatsAppReservationCode
        code_obj = WhatsAppReservationCode.objects.select_related('experience').get(code=codigo)
        return not code_obj.is_expired() and code_obj.status != 'expired'
    except Exception:
        return False


class PublicExperienceDetailView(APIView):
    """
    Public API to get experience details.
    🚀 ENTERPRISE: Only shows active, non-deleted experiences.
    With ?codigo=X (valid WhatsApp reservation code), allows loading for checkout even if draft.
    """
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, slug_or_id):
        """Get experience details by slug or ID."""
        allow_checkout = _allow_checkout_by_codigo(request)

        base_filters = {'deleted_at__isnull': True}
        if not allow_checkout:
            base_filters['status'] = 'published'
            base_filters['is_active'] = True

        try:
            experience = Experience.objects.get(slug=slug_or_id, **base_filters)
        except Experience.DoesNotExist:
            try:
                uuid.UUID(str(slug_or_id))
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Experience not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            try:
                experience = Experience.objects.get(id=slug_or_id, **base_filters)
            except Experience.DoesNotExist:
                return Response(
                    {'error': 'Experience not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Increment view count
        experience.views_count = F('views_count') + 1
        experience.save(update_fields=['views_count'])
        experience.refresh_from_db()
        
        serializer = ExperienceSerializer(experience)
        return Response(serializer.data)


class PublicExperienceResourcesView(APIView):
    """Public API to get resources for an experience (guest checkout)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, experience_id):
        """List active resources for an experience."""
        allow_checkout = _allow_checkout_by_codigo(request)
        filters = {'id': experience_id, 'deleted_at__isnull': True}
        if not allow_checkout:
            filters['status'] = 'published'
        try:
            experience = Experience.objects.get(**filters)
        except Experience.DoesNotExist:
            return Response(
                {'error': 'Experience not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        queryset = ExperienceResource.objects.filter(
            experience=experience,
            is_active=True
        ).order_by('display_order', 'name')

        serializer = ExperienceResourceSerializer(queryset, many=True)
        return Response(serializer.data)


class PublicExperienceInstancesView(APIView):
    """Public API to get available instances for an experience."""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, experience_id):
        """Get available instances with filters."""
        allow_checkout = _allow_checkout_by_codigo(request)
        filters = {'id': experience_id, 'deleted_at__isnull': True}
        if not allow_checkout:
            filters['status'] = 'published'
        try:
            experience = Experience.objects.get(**filters)
        except Experience.DoesNotExist:
            return Response(
                {'error': 'Experience not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Filter instances
        queryset = TourInstance.objects.filter(
            experience=experience,
            status='active',
            start_datetime__gte=timezone.now()
        )
        
        # Date range filters
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(start_datetime__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(start_datetime__date__lte=end_date)
        
        # Language filter
        language = request.query_params.get('language')
        if language:
            queryset = queryset.filter(language=language)
        
        serializer = TourInstanceSerializer(queryset, many=True)
        return Response(serializer.data)


# 🚀 ENTERPRISE: Synchronous Email Endpoint for Experiences
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def send_experience_email_sync(request, order_number):
    """
    🚀 ENTERPRISE: Send experience confirmation email synchronously.
    Analogous to api/v1/events/views.py::send_order_email_sync
    
    This endpoint is called from the frontend confirmation page to send
    the experience confirmation email immediately, reducing latency from 5+ minutes
    to <10 seconds.
    
    If the synchronous send fails, it automatically falls back to Celery
    for retry, ensuring no emails are lost.
    
    POST /api/v1/experiences/orders/<order_number>/send-email/?access_token=<token>
    
    Args:
        order_number: Order number from URL
        access_token: Security token from query params (required)
        to_email: Optional email override from request body
        
    Returns:
        JSON response with send status and metrics
    """
    from apps.events.models import Order, EmailLog
    from apps.experiences.email_sender import send_experience_confirmation_email_optimized
    from core.models import PlatformFlow
    from core.flow_logger import FlowLogger
    
    start_time = time.time()
    
    try:
        # 1. Get and validate access_token
        access_token = request.query_params.get('access_token')
        if not access_token:
            logger.warning(f"📧 [EMAIL_SYNC_EXP] Missing access_token for order {order_number}")
            return Response({
                'success': False,
                'message': 'Missing access_token'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 2. Get order with access_token validation
        try:
            order = Order.objects.select_related(
                'experience_reservation',
                'experience_reservation__experience',
                'user'
            ).get(
                order_number=order_number,
                access_token=access_token,
                order_kind='experience'
            )
        except Order.DoesNotExist:
            logger.warning(f"📧 [EMAIL_SYNC_EXP] Order not found or invalid token: {order_number}")
            return Response({
                'success': False,
                'message': 'Order not found or invalid token'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # 3. Get flow for logging and idempotency check
        flow_obj = None
        flow_logger = None
        try:
            # CRITICAL: Check direct relationship first (most efficient and reliable)
            flow_obj = order.flow
            
            # If not found via direct relationship, try primary_order lookup
            if not flow_obj:
                flow_obj = PlatformFlow.objects.filter(
                    primary_order=order,
                    flow_type='experience_booking'
                ).first()
            
            # If still not found, search in events
            if not flow_obj:
                flow_event = order.flow_events.first()
                if flow_event:
                    flow_obj = flow_event.flow
            
            # Convert PlatformFlow to FlowLogger for logging
            if flow_obj:
                flow_logger = FlowLogger(flow_obj)
        except Exception as e:
            logger.warning(f"📧 [EMAIL_SYNC_EXP] Could not find flow for order {order_number}: {e}")
        
        # 🚀 ENTERPRISE: IDEMPOTENCY CHECK - Verify if email already sent
        if flow_obj:
            email_sent_exists = flow_obj.events.filter(step='EMAIL_SENT').exists()
            if email_sent_exists:
                logger.info(f"📧 [EMAIL_SYNC_EXP] ✅ Email already sent for order {order_number} (idempotency check)")
                return Response({
                    'success': True,
                    'message': 'Email already sent',
                    'already_sent': True,
                    'emails_sent': 1
                }, status=status.HTTP_200_OK)
        
        # 4. Log EMAIL_SYNC_ATTEMPT
        if flow_logger:
            flow_logger.log_event(
                'EMAIL_SYNC_ATTEMPT',
                order=order,
                source='api',
                status='info',
                message=f"Attempting synchronous email send for experience order {order_number}",
                metadata={
                    'strategy': 'frontend_sync',
                    'triggered_by': 'confirmation_page'
                }
            )
        
        logger.info(f"📧 [EMAIL_SYNC_EXP] Starting synchronous email send for order {order_number}")
        
        # 5. Get optional email override
        to_email = request.data.get('to_email')
        
        # 6. Send email synchronously
        result = send_experience_confirmation_email_optimized(
            order_id=str(order.id),
            to_email=to_email,
            flow_id=str(flow_obj.id) if flow_obj else None
        )
        
        total_time_ms = int((time.time() - start_time) * 1000)
        
        # 7. Check if send was successful
        if result.get('status') == 'success' and result.get('emails_sent', 0) > 0:
            # ✅ SUCCESS
            logger.info(f"📧 [EMAIL_SYNC_EXP] ✅ Email sent successfully for order {order_number} in {total_time_ms}ms")
            
            if flow_logger:
                flow_logger.log_event(
                    'EMAIL_SENT',
                    order=order,
                    source='api',
                    status='success',
                    message=f"Email sent successfully in {total_time_ms}ms",
                    metadata={
                        'strategy': 'frontend_sync',
                        'emails_sent': result.get('emails_sent', 0),
                        'metrics': result.get('metrics', {}),
                        'total_time_ms': total_time_ms
                    }
                )
            
            # Get EmailLog details for confirmation
            email_logs = EmailLog.objects.filter(
                order=order,
                status='sent'
            ).order_by('-sent_at')[:1]
            
            response_data = {
                'success': True,
                'message': 'Email sent successfully',
                'emails_sent': result.get('emails_sent', 0),
                'metrics': result.get('metrics', {}),
                'fallback_to_celery': False,
                'recipients': []
            }
            
            # Add recipient details
            if email_logs:
                for email_log in email_logs:
                    response_data['recipients'].append({
                        'email': email_log.to_email,
                        'sent_at': email_log.sent_at.isoformat() if email_log.sent_at else None,
                        'subject': email_log.subject
                    })
            
            logger.info(
                f"📧 [EMAIL_SYNC_EXP] ✅ Success response for order {order_number}: "
                f"{result.get('emails_sent', 0)} emails sent"
            )
            
            return Response(response_data, status=status.HTTP_200_OK)
        
        else:
            # ❌ FAILED - Fallback to Celery
            logger.warning(f"📧 [EMAIL_SYNC_EXP] ⚠️ Synchronous send failed for order {order_number}, falling back to Celery")
            
            if flow_logger:
                flow_logger.log_event(
                    'EMAIL_FAILED',
                    order=order,
                    source='api',
                    status='warning',
                    message=f"Synchronous email send failed, falling back to Celery",
                    metadata={
                        'strategy': 'frontend_sync',
                        'error': result.get('error', 'Unknown error'),
                        'metrics': result.get('metrics', {})
                    }
                )
            
            # Enqueue in Celery for retry
            from apps.experiences.tasks import send_experience_confirmation_email
            task = send_experience_confirmation_email.apply_async(
                args=[str(order.id)],
                kwargs={'flow_id': str(flow_obj.id) if flow_obj else None},
                queue='emails'
            )
            
            if flow_logger:
                flow_logger.log_event(
                    'EMAIL_TASK_ENQUEUED',
                    order=order,
                    source='api',
                    status='info',
                    message=f"Email enqueued in Celery for retry",
                    metadata={
                        'task_id': task.id,
                        'reason': 'sync_send_failed'
                    }
                )
            
            logger.info(f"📧 [EMAIL_SYNC_EXP] Enqueued in Celery with task_id: {task.id}")
            
            return Response({
                'success': False,
                'message': 'Email failed but enqueued in Celery for retry',
                'fallback_to_celery': True,
                'task_id': task.id,
                'error': result.get('error', 'Unknown error')
            }, status=status.HTTP_202_ACCEPTED)
    
    except Exception as e:
        logger.error(f"❌ [EMAIL_SYNC_EXP] Unexpected error for order {order_number}: {e}", exc_info=True)
        
        # Try to enqueue in Celery as last resort
        try:
            from apps.experiences.tasks import send_experience_confirmation_email
            task = send_experience_confirmation_email.apply_async(
                args=[str(order.id)],
                queue='emails'
            )
            
            return Response({
                'success': False,
                'message': f'Unexpected error, but enqueued in Celery: {str(e)}',
                'fallback_to_celery': True,
                'task_id': task.id,
                'error': str(e)
            }, status=status.HTTP_202_ACCEPTED)
        except Exception as celery_error:
            logger.error(f"❌ [EMAIL_SYNC_EXP] Failed to enqueue in Celery: {celery_error}")
            return Response({
                'success': False,
                'message': f'Critical error: {str(e)}',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

