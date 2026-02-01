"""Views for student centers API."""

import logging
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

from apps.organizers.models import StudentCenterConfig, Organizer
from apps.experiences.models import StudentCenterTimelineItem, StudentInterest, Experience
from .serializers import (
    StudentCenterConfigSerializer,
    ExperienceSelectionSerializer,
    StudentCenterTimelineItemSerializer,
    StudentInterestSerializer,
    PublicStudentInterestSerializer
)
from core.permissions import IsOrganizer


class StudentCenterConfigView(APIView):
    """View for student center configuration."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get_organizer(self):
        """Get the current user's organizer if it's a student center."""
        organizer_user = self.request.user.organizer_roles.first()
        if not organizer_user:
            return None
        organizer = organizer_user.organizer
        if not organizer.is_student_center:
            return None
        return organizer
    
    def get(self, request):
        """Get student center configuration."""
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "No student center found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        config, created = StudentCenterConfig.objects.get_or_create(organizer=organizer)
        serializer = StudentCenterConfigSerializer(config, context={'request': request})
        return Response(serializer.data)
    
    def put(self, request):
        """Update student center configuration."""
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "No student center found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        config, created = StudentCenterConfig.objects.get_or_create(organizer=organizer)
        
        logger.info(f"✅ [StudentCenter] Updating config for organizer {organizer.id}, data: {request.data}")
        
        serializer = StudentCenterConfigSerializer(config, data=request.data, partial=True, context={'request': request})
        
        if serializer.is_valid():
            # Save the serializer data (this will save banner_image_url if provided)
            serializer.save()
            
            # Refresh from DB to get latest data
            config.refresh_from_db()
            response_data = StudentCenterConfigSerializer(config, context={'request': request}).data
            logger.info(f"✅ [StudentCenter] Config updated successfully, banner_image_url: {response_data.get('banner_image_url')}")
            return Response(response_data)
        logger.error(f"❌ [StudentCenter] Serializer errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request):
        """Partially update student center configuration."""
        return self.put(request)


class StudentCenterExperiencesView(APIView):
    """View for listing available experiences for student centers."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """List all available experiences for selection."""
        # Get query parameters
        search = request.query_params.get('search', '')
        category = request.query_params.get('category', '')
        status_filter = request.query_params.get('status', 'published')
        
        # Base queryset - all published experiences
        queryset = Experience.objects.filter(status='published', is_active=True)
        
        # Apply filters
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(short_description__icontains=search)
            )
        
        if category:
            queryset = queryset.filter(categories__contains=[category])
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Order by creation date (newest first)
        queryset = queryset.order_by('-created_at')
        
        serializer = ExperienceSelectionSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


class StudentCenterTimelineViewSet(viewsets.ModelViewSet):
    """ViewSet for student center timeline items."""
    
    serializer_class = StudentCenterTimelineItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_organizer(self):
        """Get the current user's organizer if it's a student center."""
        organizer_user = self.request.user.organizer_roles.first()
        if not organizer_user:
            return None
        organizer = organizer_user.organizer
        if not organizer.is_student_center:
            return None
        return organizer
    
    def get_queryset(self):
        """Get timeline items for the current student center."""
        organizer = self.get_organizer()
        if not organizer:
            return StudentCenterTimelineItem.objects.none()
        return StudentCenterTimelineItem.objects.filter(student_center=organizer)
    
    def create(self, request, *args, **kwargs):
        """Create a new timeline item with better error handling."""
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "No student center found for this user."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        logger.info(f"✅ [StudentCenter] Creating timeline item for organizer {organizer.id}")
        logger.info(f"✅ [StudentCenter] Request data: {request.data}")
        
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            logger.error(f"❌ [StudentCenter] Serializer errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info(f"✅ [StudentCenter] Serializer validated data: {serializer.validated_data}")
        
        try:
            serializer.save(student_center=organizer)
            logger.info(f"✅ [StudentCenter] Timeline item created successfully: {serializer.instance.id}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"❌ [StudentCenter] Error saving timeline item: {str(e)}")
            return Response(
                {"detail": f"Error creating timeline item: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm a timeline item when threshold is reached."""
        timeline_item = self.get_object()
        
        if timeline_item.status == 'confirmed':
            return Response(
                {"detail": "This timeline item is already confirmed."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not timeline_item.can_confirm():
            return Response(
                {
                    "detail": f"Threshold not reached. Need {timeline_item.interest_threshold} interested students, currently have {timeline_item.get_interested_count()}."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        timeline_item.status = 'confirmed'
        timeline_item.save()
        
        serializer = self.get_serializer(timeline_item)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get', 'post'])
    def interests(self, request, pk=None):
        """Get or create interests for a timeline item."""
        timeline_item = self.get_object()
        
        if request.method == 'GET':
            # Get interests (requires authentication for organizer)
            interests = StudentInterest.objects.filter(timeline_item=timeline_item)
            serializer = StudentInterestSerializer(interests, many=True)
            return Response(serializer.data)
        
        elif request.method == 'POST':
            # Register interest (public, no auth required)
            serializer = StudentInterestSerializer(data=request.data)
            if serializer.is_valid():
                # Check if email already registered for this timeline item
                existing = StudentInterest.objects.filter(
                    timeline_item=timeline_item,
                    email=serializer.validated_data['email']
                ).first()
                
                if existing:
                    return Response(
                        {"detail": "Ya has registrado tu interés en esta experiencia."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                serializer.save(timeline_item=timeline_item)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentCenterUploadView(APIView):
    """View for uploading student center assets (logo, banner)."""
    
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def get_organizer(self):
        """Get the current user's organizer if it's a student center."""
        organizer_user = self.request.user.organizer_roles.first()
        if not organizer_user:
            return None
        organizer = organizer_user.organizer
        if not organizer.is_student_center:
            return None
        return organizer
    
    def post(self, request):
        """Upload an image file for student center."""
        organizer = self.get_organizer()
        if not organizer:
            return Response(
                {"detail": "No student center found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        file_obj = request.FILES.get('file')
        asset_type = request.data.get('type', 'banner')  # 'logo' or 'banner'
        
        if not file_obj:
            return Response(
                {"detail": "No file provided."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file type
        if not file_obj.content_type.startswith('image/'):
            return Response(
                {"detail": "File must be an image."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file size (max 10MB)
        if file_obj.size > 10 * 1024 * 1024:
            return Response(
                {"detail": "File size must be less than 10MB."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Generate filename
            import uuid
            filename = f"{asset_type}_{uuid.uuid4()}_{file_obj.name}"
            file_path = f"student_centers/{asset_type}s/{filename}"
            
            # Save file
            saved_path = default_storage.save(file_path, file_obj)
            file_url = default_storage.url(saved_path)
            
            # Update config based on asset type
            config, created = StudentCenterConfig.objects.get_or_create(organizer=organizer)
            
            if asset_type == 'logo':
                organizer.logo = saved_path
                organizer.save()
            elif asset_type == 'banner':
                config.banner_image = saved_path
                config.save()
            
            return Response({
                'url': file_url,
                'file_path': saved_path,
                'type': asset_type
            })
        
        except Exception as e:
            return Response(
                {"detail": f"Error uploading file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PublicStudentCenterView(APIView):
    """Public view for student center pages (no authentication required)."""
    
    permission_classes = [AllowAny]
    
    def get(self, request, slug):
        """Get public student center data by organizer slug."""
        try:
            organizer = Organizer.objects.get(slug=slug, is_student_center=True)
        except Organizer.DoesNotExist:
            return Response(
                {"detail": "Student center not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get config
        try:
            config = StudentCenterConfig.objects.get(organizer=organizer)
            config_data = StudentCenterConfigSerializer(config, context={'request': request}).data
        except StudentCenterConfig.DoesNotExist:
            config_data = None
        
        # Get timeline items (only confirmed or tentative)
        # Order by scheduled_date first (chronological), then by display_order as tiebreaker
        timeline_items = StudentCenterTimelineItem.objects.filter(
            student_center=organizer,
            status__in=['tentative', 'confirmed']
        ).order_by('scheduled_date', 'display_order')
        
        timeline_data = StudentCenterTimelineItemSerializer(
            timeline_items,
            many=True,
            context={'request': request}
        ).data
        
        # Get logo URL
        logo_url = None
        if organizer.logo:
            if hasattr(organizer.logo, 'url'):
                logo_url = request.build_absolute_uri(organizer.logo.url)
            else:
                logo_url = str(organizer.logo)
        
        # Get selected experiences if config exists
        selected_experiences_data = []
        if config_data and config_data.get('selected_experiences'):
            experience_ids = config_data.get('selected_experiences', [])
            if experience_ids:
                from .serializers import ExperienceSelectionSerializer
                experiences = Experience.objects.filter(id__in=experience_ids, status='published', is_active=True)
                selected_experiences_data = ExperienceSelectionSerializer(
                    experiences,
                    many=True,
                    context={'request': request}
                ).data
        
        return Response({
            'organizer': {
                'id': str(organizer.id),
                'name': organizer.name,
                'slug': organizer.slug,
                'logo': logo_url,
            },
            'config': config_data,
            'timeline_items': timeline_data,
            'selected_experiences': selected_experiences_data,
        })


class PublicTimelineItemInterestsView(APIView):
    """
    🚀 ENTERPRISE: Public view for registering interest (no authentication required).
    
    This endpoint allows students to register their interest in a timeline item.
    The timeline_item is provided via URL parameter and set automatically.
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request, timeline_item_id):
        """Register interest in a timeline item."""
        # Get timeline item
        try:
            timeline_item = StudentCenterTimelineItem.objects.get(id=timeline_item_id)
        except StudentCenterTimelineItem.DoesNotExist:
            logger.warning(f"❌ [PublicTimelineItemInterests] Timeline item not found: {timeline_item_id}")
            return Response(
                {"detail": "Timeline item not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate timeline item is active
        if timeline_item.status not in ['tentative', 'confirmed']:
            logger.warning(f"❌ [PublicTimelineItemInterests] Timeline item not active: {timeline_item_id}, status: {timeline_item.status}")
            return Response(
                {"detail": "Esta experiencia no está disponible para registro de interés."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use public serializer for validation (excludes timeline_item)
        serializer = PublicStudentInterestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"❌ [PublicTimelineItemInterests] Validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        email = validated_data['email']
        
        # Check if email already registered for this timeline item
        existing = StudentInterest.objects.filter(
            timeline_item=timeline_item,
            email=email
        ).first()
        
        if existing:
            logger.info(f"⚠️ [PublicTimelineItemInterests] Duplicate interest: {email} for timeline {timeline_item_id}")
            return Response(
                {"detail": "Ya has registrado tu interés en esta experiencia."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create interest with validated data
        try:
            interest = StudentInterest.objects.create(
                timeline_item=timeline_item,
                name=validated_data['name'],
                email=email,
                phone=validated_data.get('phone') or None,
                status='pending'
            )
            
            logger.info(f"✅ [PublicTimelineItemInterests] Interest created: {interest.id} for timeline {timeline_item_id}")
            
            # 🚀 ENTERPRISE: Send confirmation email
            try:
                from .email_sender import send_student_interest_confirmation_email
                email_result = send_student_interest_confirmation_email(str(interest.id))
                if email_result.get('status') == 'success':
                    logger.info(f"📧 [PublicTimelineItemInterests] Confirmation email sent to {email}")
                else:
                    logger.warning(f"⚠️ [PublicTimelineItemInterests] Email send failed: {email_result.get('error')}")
            except Exception as email_error:
                # Don't fail the request if email fails
                logger.error(f"❌ [PublicTimelineItemInterests] Error sending email: {email_error}", exc_info=True)
            
            # Serialize for response using full serializer
            response_serializer = StudentInterestSerializer(interest)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"❌ [PublicTimelineItemInterests] Error creating interest: {e}", exc_info=True)
            return Response(
                {"detail": "Error al registrar interés. Por favor, intenta nuevamente."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

