"""Views for experiences API."""

import logging
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone

from apps.experiences.models import Experience, TourLanguage, TourInstance, TourBooking, OrganizerCredit
from apps.experiences.serializers import (
    ExperienceSerializer,
    TourLanguageSerializer,
    TourInstanceSerializer,
    TourBookingSerializer,
    TourBookingCreateSerializer,
    OrganizerCreditSerializer
)
from apps.organizers.models import OrganizerUser
from core.permissions import HasExperienceModule

logger = logging.getLogger(__name__)


class ExperienceViewSet(viewsets.ModelViewSet):
    """ViewSet for Experience model."""
    
    queryset = Experience.objects.all()
    serializer_class = ExperienceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
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
        """Return experiences based on user permissions."""
        organizer = self.get_organizer()
        
        # If user is an organizer, return their experiences
        if organizer:
            return self.queryset.filter(organizer=organizer)
        
        # For public access (retrieve only)
        if self.action == 'retrieve':
            return Experience.objects.filter(status='published')
        
        # Otherwise return empty
        return Experience.objects.none()
    
    def get_permissions(self):
        """Allow public access to retrieve endpoint."""
        if self.action == 'retrieve':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), HasExperienceModule()]
    
    def get_serializer_context(self):
        """Add additional context to serializer."""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


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
        return TourInstance.objects.none()
    
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

