"""Views for terminal API."""

import logging
import os
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import (
    TerminalCompany, TerminalRoute, TerminalTrip, TerminalExcelUpload,
    TerminalDestination, TerminalAdvertisingSpace, TerminalAdvertisingInteraction,
    TerminalDestinationExperienceConfig
)
from .serializers import (
    TerminalCompanySerializer,
    TerminalRouteSerializer,
    TerminalTripSerializer,
    TerminalExcelUploadSerializer,
    TerminalDestinationSerializer,
    TerminalAdvertisingSpaceSerializer,
    TerminalAdvertisingInteractionSerializer,
    TerminalDestinationExperienceConfigSerializer
)
from .services.excel_parser.file_parser import process_excel_trips
from .services.destination_service import (
    create_or_update_destinations_from_routes,
    get_destinations_from_routes
)
from .services.advertising_service import (
    track_interaction,
    get_active_spaces
)
from .permissions import IsTerminalAdmin
from .pagination import TerminalTripPagination

logger = logging.getLogger(__name__)


class TerminalCompanyViewSet(viewsets.ModelViewSet):
    """ViewSet for TerminalCompany."""
    
    queryset = TerminalCompany.objects.all()
    serializer_class = TerminalCompanySerializer
    
    def get_permissions(self):
        """Public read access, admin write access (temporary)."""
        if self.action in ['list', 'retrieve']:
            return []  # Public read access
        return [IsTerminalAdmin()]  # Admin required for write operations
    
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'contact_method', 'booking_method']
    search_fields = ['name', 'phone', 'email']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class TerminalRouteViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for TerminalRoute (read-only)."""
    
    queryset = TerminalRoute.objects.all()
    serializer_class = TerminalRouteSerializer
    permission_classes = []  # Public read access (temporary)
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['origin', 'destination']
    search_fields = ['origin', 'destination']
    
    @action(detail=False, methods=['get'])
    def locations(self, request):
        """Get unique origins and destinations from all routes."""
        origins = TerminalRoute.objects.values_list('origin', flat=True).distinct().order_by('origin')
        destinations = TerminalRoute.objects.values_list('destination', flat=True).distinct().order_by('destination')
        
        # Combine and deduplicate
        all_locations = sorted(set(list(origins) + list(destinations)))
        
        return Response({
            'origins': list(origins),
            'destinations': list(destinations),
            'all': all_locations,
        })


class TerminalTripViewSet(viewsets.ModelViewSet):
    """ViewSet for TerminalTrip."""
    
    queryset = TerminalTrip.objects.select_related('company', 'route').all()
    serializer_class = TerminalTripSerializer
    pagination_class = TerminalTripPagination
    
    def get_permissions(self):
        """Public read access, public write access temporarily."""
        # TODO: Add proper authentication later
        return []  # Temporary: allow public access to all operations
    
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['trip_type', 'status', 'is_active', 'company', 'date', 'route__origin', 'route__destination']
    search_fields = ['route__origin', 'route__destination', 'license_plate', 'company__name']
    ordering_fields = ['date', 'departure_time', 'arrival_time']
    ordering = ['date', 'departure_time', 'arrival_time']
    
    def get_queryset(self):
        """Filter out inactive and sold out trips for public access."""
        queryset = super().get_queryset()
        
        # For public access (list/retrieve), only show active trips
        if self.action in ['list', 'retrieve']:
            # Check if user is authenticated and has admin permissions
            is_admin = (
                self.request.user and 
                self.request.user.is_authenticated and 
                (self.request.user.is_superuser or 
                 (hasattr(self.request.user, 'is_staff') and self.request.user.is_staff))
            )
            
            if not is_admin:
                # Public or non-admin: only active trips, not sold out
                queryset = queryset.filter(is_active=True).exclude(status='sold_out')
        
        return queryset
    
    def get_permissions(self):
        """Public read access, admin write access."""
        if self.action in ['list', 'retrieve']:
            return []  # No authentication required for public trips
        # For write operations (create, update, delete, sold_out), allow public temporarily
        # TODO: Add proper authentication later
        return []  # Temporary: allow public access to all operations
        # return [IsTerminalAdmin()]  # Admin required for create/update/delete
    
    @action(detail=True, methods=['patch'])
    def sold_out(self, request, pk=None):
        """Mark trip as sold out (sets status='sold_out' and is_active=False)."""
        trip = self.get_object()
        
        trip.status = 'sold_out'
        trip.is_active = False
        # Do NOT modify available_seats (remains NULL in v1)
        trip.save()
        
        serializer = self.get_serializer(trip)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """Delete multiple trips at once."""
        trip_ids = request.data.get('ids', [])
        
        if not trip_ids:
            return Response(
                {'error': 'No trip IDs provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            deleted_count = TerminalTrip.objects.filter(id__in=trip_ids).delete()[0]
            return Response({
                'deleted_count': deleted_count,
                'message': f'Successfully deleted {deleted_count} trip(s)'
            })
        except Exception as e:
            logger.error(f"Error deleting trips: {e}", exc_info=True)
            return Response(
                {'error': f'Error deleting trips: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TerminalExcelUploadViewSet(viewsets.ModelViewSet):
    """ViewSet for TerminalExcelUpload."""
    
    queryset = TerminalExcelUpload.objects.select_related('uploaded_by').all()
    serializer_class = TerminalExcelUploadSerializer
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'upload_type']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_permissions(self):
        """Public access for upload_excel and preview_excel, admin for other actions."""
        if self.action in ['upload_excel', 'preview_excel']:
            return []  # No authentication required for upload (temporary)
        return [IsTerminalAdmin()]  # Admin required for other actions
    
    @action(detail=False, methods=['post'])
    def preview_excel(self, request):
        """
        Preview Excel file without saving to database.
        
        Expected form data:
        - file: Excel file (.xlsx)
        - upload_type: 'departures' or 'arrivals'
        - date_range_start: YYYY-MM-DD
        - date_range_end: YYYY-MM-DD
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file_obj = request.FILES['file']
        upload_type = request.data.get('upload_type')
        date_range_start_str = request.data.get('date_range_start')
        date_range_end_str = request.data.get('date_range_end')
        
        # Validate required fields
        if not upload_type or upload_type not in ['departures', 'arrivals']:
            return Response(
                {'error': 'upload_type must be "departures" or "arrivals"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not date_range_start_str or not date_range_end_str:
            return Response(
                {'error': 'date_range_start and date_range_end are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file extension
        if not file_obj.name.endswith('.xlsx'):
            return Response(
                {'error': 'File must be .xlsx format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse dates
        try:
            date_range_start = datetime.strptime(date_range_start_str, '%Y-%m-%d').date()
            date_range_end = datetime.strptime(date_range_end_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            logger.info(f"🔍 [preview_excel] Starting preview for file: {file_obj.name}")
            logger.info(f"📋 [preview_excel] Upload type: {upload_type}, Date range: {date_range_start} to {date_range_end}")
            
            from .services.excel_parser.preview_service import preview_excel_upload
            preview_result = preview_excel_upload(
                file_obj=file_obj,
                upload_type=upload_type,
                date_range_start=date_range_start,
                date_range_end=date_range_end
            )
            
            logger.info(f"✅ [preview_excel] Preview completed successfully")
            logger.info(f"📊 [preview_excel] Summary: {preview_result.get('summary', {})}")
            logger.info(f"🗺️  [preview_excel] Column mapping: {preview_result.get('column_mapping', {})}")
            logger.info(f"📄 [preview_excel] Processed sheets: {preview_result.get('processed_sheets', [])}")
            logger.info(f"❌ [preview_excel] Errors: {len(preview_result.get('errors', []))} errors")
            
            # Ensure all keys are present and properly formatted
            response_data = {
                'column_mapping': preview_result.get('column_mapping', {}),
                'trips_preview': preview_result.get('trips_preview', []),
                'existing_trips': preview_result.get('existing_trips', []),
                'new_trips': preview_result.get('new_trips', []),
                'processed_sheets': preview_result.get('processed_sheets', []),
                'errors': preview_result.get('errors', []),
                'summary': preview_result.get('summary', {}),
            }
            
            logger.info(f"📤 [preview_excel] Sending response with column_mapping keys: {list(response_data.get('column_mapping', {}).keys())}")
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error previewing Excel upload: {e}", exc_info=True)
            return Response(
                {'error': f'Error previewing file: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def upload_excel(self, request):
        """
    Upload and process Excel file.
    
    Expected form data:
    - file: Excel file (.xlsx)
    - upload_type: 'departures' or 'arrivals'
    - date_range_start: YYYY-MM-DD
    - date_range_end: YYYY-MM-DD
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file_obj = request.FILES['file']
        upload_type = request.data.get('upload_type')
        date_range_start_str = request.data.get('date_range_start')
        date_range_end_str = request.data.get('date_range_end')
        
        # Validate required fields
        if not upload_type or upload_type not in ['departures', 'arrivals']:
            return Response(
                {'error': 'upload_type must be "departures" or "arrivals"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not date_range_start_str or not date_range_end_str:
            return Response(
                {'error': 'date_range_start and date_range_end are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file extension
        if not file_obj.name.endswith('.xlsx'):
            return Response(
                {'error': 'File must be .xlsx format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse dates
        try:
            date_range_start = datetime.strptime(date_range_start_str, '%Y-%m-%d').date()
            date_range_end = datetime.strptime(date_range_end_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create upload record
        # Note: uploaded_by is None for public uploads (temporary until auth is implemented)
        upload_record = TerminalExcelUpload.objects.create(
            file_name=file_obj.name,
            file_path=file_obj,
            upload_type=upload_type,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            status='processing',
            uploaded_by=request.user if (request.user and request.user.is_authenticated) else None
        )
        
        try:
            # Process Excel file
            file_path = upload_record.file_path.path
            result = process_excel_trips(
                file_path=file_path,
                upload_type=upload_type,
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                uploaded_by=request.user if (request.user and request.user.is_authenticated) else None
            )
            
            # Update upload record
            upload_record.status = 'completed'
            upload_record.trips_created = result['trips_created']
            upload_record.trips_updated = result['trips_updated']
            upload_record.processed_sheets = result['processed_sheets']
            upload_record.errors = result['errors']
            upload_record.save()
            
            return Response({
                'status': 'completed',
                'tripsCreated': result['trips_created'],
                'tripsUpdated': result['trips_updated'],
                'createdTrips': result.get('created_trips', []),  # List of created trips
                'updatedTrips': result.get('updated_trips', []),  # List of updated trips
                'errors': result['errors'],
                'processedSheets': result['processed_sheets'],
                'uploadId': str(upload_record.id)
            })
            
        except Exception as e:
            logger.error(f"Error processing Excel upload: {e}", exc_info=True)
            upload_record.status = 'failed'
            upload_record.errors = [str(e)]
            upload_record.save()
            
            return Response(
                {'error': f'Error processing file: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TerminalDestinationViewSet(viewsets.ModelViewSet):
    """ViewSet for TerminalDestination."""
    
    queryset = TerminalDestination.objects.all()
    serializer_class = TerminalDestinationSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'created_from_excel']
    search_fields = ['name', 'region']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_permissions(self):
        """Public access for all operations (temporary - no auth yet)."""
        return []  # Public access for all operations
    
    @action(detail=False, methods=['get'])
    def from_routes(self, request):
        """Get unique destinations from routes and optionally create/update them."""
        create = request.query_params.get('create', 'false').lower() == 'true'
        
        if create:
            result = create_or_update_destinations_from_routes()
            return Response({
                'message': 'Destinations created/updated from routes',
                'created': result['created'],
                'updated': result['updated'],
                'total': result['total']
            })
        else:
            locations = get_destinations_from_routes()
            return Response(locations)


class TerminalAdvertisingSpaceViewSet(viewsets.ModelViewSet):
    """ViewSet for TerminalAdvertisingSpace."""
    
    queryset = TerminalAdvertisingSpace.objects.select_related('destination', 'experience').all()
    serializer_class = TerminalAdvertisingSpaceSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['space_type', 'destination', 'is_active', 'route_origin', 'route_destination']
    search_fields = ['position', 'banner_title', 'banner_subtitle']
    ordering_fields = ['order', 'created_at']
    ordering = ['order', 'created_at']
    
    def get_permissions(self):
        """Public access for all operations (temporary - no auth yet)."""
        return []  # Public access for all operations
    
    @action(detail=True, methods=['post'])
    def track(self, request, pk=None):
        """Track an interaction with this advertising space."""
        space = self.get_object()
        interaction_type = request.data.get('interaction_type', 'view')
        
        if interaction_type not in ['view', 'click', 'impression']:
            return Response(
                {'error': 'Invalid interaction_type. Must be "view", "click", or "impression".'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get client info
        user_ip = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        referrer = request.META.get('HTTP_REFERER', '')
        destination = request.data.get('destination')
        
        try:
            interaction = track_interaction(
                advertising_space_id=str(space.id),
                interaction_type=interaction_type,
                user_ip=user_ip,
                user_agent=user_agent,
                referrer=referrer,
                destination=destination
            )
            serializer = TerminalAdvertisingInteractionSerializer(interaction)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error tracking interaction: {e}", exc_info=True)
            return Response(
                {'error': f'Error tracking interaction: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class TerminalDestinationExperienceConfigViewSet(viewsets.ModelViewSet):
    """ViewSet for TerminalDestinationExperienceConfig."""
    
    queryset = TerminalDestinationExperienceConfig.objects.select_related('destination', 'experience').all()
    serializer_class = TerminalDestinationExperienceConfigSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['destination', 'is_featured', 'is_active']
    ordering_fields = ['order', 'created_at']
    ordering = ['order', 'created_at']
    
    def get_permissions(self):
        """Public access for all operations (temporary - no auth yet)."""
        return []  # Public access for all operations


# Public endpoints (no authentication required)
from rest_framework.views import APIView


class PublicAdvertisingSpacesView(APIView):
    """Public endpoint to get active advertising spaces."""
    
    permission_classes = []  # No authentication required
    
    def get(self, request):
        """Get active advertising spaces with optional filters."""
        space_type = request.query_params.get('space_type')
        destination_id = request.query_params.get('destination_id')
        route_origin = request.query_params.get('route_origin')
        route_destination = request.query_params.get('route_destination')
        
        spaces = get_active_spaces(
            space_type=space_type,
            destination_id=destination_id,
            route_origin=route_origin,
            route_destination=route_destination,
            include_expired=False
        )
        
        serializer = TerminalAdvertisingSpaceSerializer(spaces, many=True)
        return Response(serializer.data)


class PublicDestinationExperiencesView(APIView):
    """Public endpoint to get experiences for a destination."""
    
    permission_classes = []  # No authentication required
    
    def get(self, request, slug):
        """Get featured experiences for a destination by slug."""
        try:
            destination = TerminalDestination.objects.get(slug=slug, is_active=True)
        except TerminalDestination.DoesNotExist:
            return Response(
                {'error': 'Destination not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get featured experiences for this destination
        configs = TerminalDestinationExperienceConfig.objects.filter(
            destination=destination,
            is_featured=True,
            is_active=True
        ).select_related('experience').order_by('order')
        
        # Filter out deleted or inactive experiences
        experiences = []
        for config in configs:
            if config.experience and config.experience.is_active and not config.experience.deleted_at:
                serializer = TerminalDestinationExperienceConfigSerializer(config)
                experiences.append(serializer.data)
        
        return Response({
            'destination': TerminalDestinationSerializer(destination).data,
            'experiences': experiences
        })

