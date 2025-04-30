"""Views for events API."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from core.permissions import IsOrganizer, HasEventModule
from apps.events.models import (
    Event,
    EventCategory,
    Location,
    TicketTier,
)
from .serializers import (
    EventListSerializer,
    EventDetailSerializer,
    EventCreateUpdateSerializer,
    EventCategorySerializer,
    LocationSerializer,
    TicketTierSerializer,
)


class EventViewSet(viewsets.ModelViewSet):
    """
    API endpoint for events.
    """
    filterset_fields = ['status', 'type', 'featured', 'organizer']
    search_fields = ['title', 'description', 'short_description', 'tags']
    ordering_fields = ['start_date', 'end_date', 'created_at', 'title']
    ordering = ['-start_date']
    
    def get_queryset(self):
        """
        Get queryset based on permission.
        """
        # Public events for non-authenticated users or non-organizers
        if not self.request.user.is_authenticated or not hasattr(self.request.user, 'organizer'):
            return Event.objects.filter(status='published')
        
        # All events for the organizer
        return Event.objects.filter(organizer=self.request.user.organizer)
    
    def get_serializer_class(self):
        """
        Return appropriate serializer class.
        """
        if self.action == 'list':
            return EventListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return EventCreateUpdateSerializer
        return EventDetailSerializer
    
    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsOrganizer(), HasEventModule()]
    
    @extend_schema(
        parameters=[
            OpenApiParameter(name='start_date', description='Filter by start date', type=str),
            OpenApiParameter(name='end_date', description='Filter by end date', type=str),
            OpenApiParameter(name='location', description='Filter by location', type=str),
            OpenApiParameter(name='category', description='Filter by category', type=str),
        ]
    )
    def list(self, request, *args, **kwargs):
        """
        List events with filtering options.
        """
        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated()])
    def favorite(self, request, pk=None):
        """
        Add/remove event to/from favorites.
        """
        # This can be implemented when we have a favorites model
        return Response({"detail": "Favorites functionality not implemented yet."}, status=status.HTTP_501_NOT_IMPLEMENTED)
    
    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny()])
    def availability(self, request, pk=None):
        """
        Get ticket availability for an event.
        """
        event = self.get_object()
        ticket_tiers = event.ticket_tiers.all()
        
        data = {
            'event_id': event.id,
            'event_title': event.title,
            'ticket_tiers': []
        }
        
        for tier in ticket_tiers:
            if tier.is_public:
                data['ticket_tiers'].append({
                    'id': tier.id,
                    'name': tier.name,
                    'available': tier.available,
                    'capacity': tier.capacity,
                    'is_sold_out': tier.available <= 0
                })
        
        return Response(data)


class EventCategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for event categories.
    """
    queryset = EventCategory.objects.all()
    serializer_class = EventCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    ordering = ['name']


class LocationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for locations.
    """
    serializer_class = LocationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['city', 'country']
    search_fields = ['name', 'address', 'city', 'country']
    ordering_fields = ['name', 'city', 'country']
    ordering = ['name']
    
    def get_queryset(self):
        """
        Get locations for the current organizer if authenticated.
        """
        if not self.request.user.is_authenticated or not hasattr(self.request.user, 'organizer'):
            return Location.objects.filter(events__status='published').distinct()
        
        return Location.objects.filter(tenant_id=self.request.user.organizer.schema_name)
    
    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsOrganizer()]


class TicketTierViewSet(viewsets.ModelViewSet):
    """
    API endpoint for ticket tiers.
    """
    serializer_class = TicketTierSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'type', 'is_public']
    ordering_fields = ['price', 'name']
    ordering = ['price']
    
    def get_queryset(self):
        """
        Get ticket tiers based on permissions.
        """
        # For public access, only return public ticket tiers for published events
        if not self.request.user.is_authenticated or not hasattr(self.request.user, 'organizer'):
            return TicketTier.objects.filter(
                event__status='published',
                is_public=True
            )
        
        # For organizers, return all their ticket tiers
        return TicketTier.objects.filter(
            event__organizer=self.request.user.organizer
        )
    
    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsOrganizer(), HasEventModule()] 