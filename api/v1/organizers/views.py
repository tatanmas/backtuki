"""Views for organizers API."""

from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from core.permissions import IsSuperAdmin, IsOrganizer
from apps.organizers.models import (
    Organizer,
    OrganizerUser,
    OrganizerSubscription,
)
from .serializers import (
    OrganizerSerializer,
    OrganizerDetailSerializer,
    OrganizerUserSerializer,
    OrganizerSubscriptionSerializer,
)


class OrganizerViewSet(viewsets.ModelViewSet):
    """
    API endpoint for organizers.
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['has_events_module', 'has_accommodation_module', 'has_experience_module']
    search_fields = ['name', 'slug', 'description', 'city', 'country']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        """
        Get queryset based on permission.
        """
        # Superadmin can see all organizers
        if self.request.user.is_superuser:
            return Organizer.objects.all()
        
        # Organizer users can only see their own organizer
        if self.request.user.is_authenticated and hasattr(self.request.user, 'organizer_roles'):
            organizer_ids = self.request.user.organizer_roles.values_list('organizer_id', flat=True)
            return Organizer.objects.filter(id__in=organizer_ids)
        
        # Others can only see organizers with published events
        return Organizer.objects.filter(events__status='published').distinct()
    
    def get_serializer_class(self):
        """
        Return appropriate serializer class.
        """
        if self.action == 'retrieve':
            return OrganizerDetailSerializer
        return OrganizerSerializer
    
    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsSuperAdmin()]
        return [permissions.IsAuthenticated(), IsOrganizer()]
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated(), IsOrganizer()])
    def toggle_module(self, request, pk=None):
        """
        Toggle a module for an organizer.
        """
        organizer = self.get_object()
        
        # Check if user belongs to this organizer
        if not request.user.organizer_roles.filter(organizer=organizer, is_admin=True).exists():
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        module = request.data.get('module')
        activate = request.data.get('activate', True)
        
        if module == 'events':
            organizer.has_events_module = activate
        elif module == 'accommodations':
            organizer.has_accommodation_module = activate
        elif module == 'experiences':
            organizer.has_experience_module = activate
        else:
            return Response(
                {"detail": "Invalid module name."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        organizer.save()
        return Response(OrganizerSerializer(organizer).data)
    
    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated(), IsOrganizer()])
    def users(self, request, pk=None):
        """
        Get users for an organizer.
        """
        organizer = self.get_object()
        
        # Check if user belongs to this organizer
        if not request.user.organizer_roles.filter(organizer=organizer).exists():
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        organizer_users = organizer.organizer_users.all()
        serializer = OrganizerUserSerializer(organizer_users, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated(), IsOrganizer()])
    def subscriptions(self, request, pk=None):
        """
        Get subscriptions for an organizer.
        """
        organizer = self.get_object()
        
        # Check if user belongs to this organizer
        if not request.user.organizer_roles.filter(organizer=organizer).exists():
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        subscriptions = organizer.subscriptions.all()
        serializer = OrganizerSubscriptionSerializer(subscriptions, many=True)
        return Response(serializer.data) 