"""Views for organizers API."""

from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import NotFound
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
import re

from apps.organizers.models import (
    Organizer,
    OrganizerOnboarding,
    BillingDetails,
    BankingDetails,
    OrganizerUser,
    OrganizerSubscription
)
from .serializers import (
    OrganizerSerializer,
    OrganizerOnboardingSerializer,
    BillingDetailsSerializer,
    BankingDetailsSerializer,
    OrganizerUserSerializer,
    OrganizerSubscriptionSerializer
)
from core.permissions import IsOrganizer

User = get_user_model()


class OrganizerViewSet(viewsets.ModelViewSet):
    """
    API endpoint for organizers.
    """
    serializer_class = OrganizerSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get queryset based on user permissions."""
        if self.request.user.is_staff:
            return Organizer.objects.all()
        elif hasattr(self.request.user, 'organizer_roles'):
            return Organizer.objects.filter(organizer_users__user=self.request.user)
        return Organizer.objects.none()
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current user's organizer."""
        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Try to get organizer from user's organizer_roles
        try:
            organizer_user = request.user.organizer_roles.first()
            if organizer_user:
                serializer = self.get_serializer(organizer_user.organizer)
                return Response(serializer.data)
            else:
                return Response(
                    {"detail": "No organizer found for this user."},
                    status=status.HTTP_404_NOT_FOUND
                )
        except Exception as e:
            return Response(
                {"detail": f"Error retrieving organizer: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class CurrentOnboardingView(APIView):
    """
    Get or create the current onboarding process.
    If an onboarding_id is provided, it retrieves that instance.
    Otherwise, it creates a new one.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        onboarding_id = request.query_params.get('id')
        if onboarding_id:
            onboarding = get_object_or_404(OrganizerOnboarding, id=onboarding_id)
        else:
            onboarding = OrganizerOnboarding.objects.create()
        
        serializer = OrganizerOnboardingSerializer(onboarding)
        return Response(serializer.data)


class OnboardingStepView(APIView):
    """
    Save a specific step of the onboarding process.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        onboarding_id = request.data.get('onboarding_id')
        step = request.data.get('step')
        data = request.data.get('data', {})

        if not all([onboarding_id, step, isinstance(data, dict)]):
            return Response(
                {"detail": "Invalid request. 'onboarding_id', 'step', and 'data' are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        onboarding = get_object_or_404(OrganizerOnboarding, id=onboarding_id)

        # Use snake_case keys to match frontend payload
        if step == 1:
            onboarding.selected_types = data.get('selected_types', onboarding.selected_types)
        elif step == 2:
            onboarding.organization_name = data.get('organization_name', onboarding.organization_name)
            onboarding.organization_slug = data.get('organization_slug', onboarding.organization_slug)
            onboarding.organization_size = data.get('organization_size', onboarding.organization_size)
        elif step == 3:
            onboarding.contact_name = data.get('contact_name', onboarding.contact_name)
            onboarding.contact_email = data.get('contact_email', onboarding.contact_email)
            onboarding.contact_phone = data.get('contact_phone', onboarding.contact_phone)
        
        onboarding.completed_step = max(onboarding.completed_step or 0, int(step))
        onboarding.save()
                
        serializer = OrganizerOnboardingSerializer(onboarding)
        return Response(serializer.data)


class OnboardingCompleteView(APIView):
    """
    Complete the onboarding process and create the organizer and user.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        onboarding_id = request.data.get('onboarding_id')
        
        if not onboarding_id:
            return Response(
                {"detail": "Invalid request. 'onboarding_id' is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        onboarding = get_object_or_404(OrganizerOnboarding, id=onboarding_id)
        
        # Validate that all required fields are present
        required_fields = [
            'selected_types', 'organization_name', 'organization_slug', 
            'contact_name', 'contact_email'
        ]
        
        missing_fields = []
        for field in required_fields:
            if not getattr(onboarding, field):
                missing_fields.append(field)
        
        if missing_fields:
            return Response(
                {"detail": f"Missing required fields: {', '.join(missing_fields)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Create the organizer
                organizer = Organizer.objects.create(
                    name=onboarding.organization_name,
                    slug=onboarding.organization_slug,
                    contact_email=onboarding.contact_email,
                    contact_phone=onboarding.contact_phone or '',
                    organization_size=onboarding.organization_size or 'small',
                    representative_name=onboarding.contact_name,
                    representative_email=onboarding.contact_email,
                    representative_phone=onboarding.contact_phone or '',
                    has_events_module='eventos' in (onboarding.selected_types or []),
                    has_experience_module='experiencias' in (onboarding.selected_types or []),
                    has_accommodation_module='alojamientos' in (onboarding.selected_types or []),
                    status='active'
                )
                
                # Create the user (provide username as email)
                user = User.objects.create_user(
                    username=onboarding.contact_email,  # Use email as username
                    email=onboarding.contact_email,
                    password=request.data.get('password'),  # Password should be provided in request
                    first_name=onboarding.contact_name.split()[0] if onboarding.contact_name else '',
                    last_name=' '.join(onboarding.contact_name.split()[1:]) if onboarding.contact_name and len(onboarding.contact_name.split()) > 1 else '',
                    is_active=True
                )
                
                # Link user to organizer
                OrganizerUser.objects.create(
                    organizer=organizer,
                    user=user,
                    is_admin=True,
                    can_manage_events=True,
                    can_manage_accommodations=True,
                    can_manage_experiences=True,
                    can_view_reports=True,
                    can_manage_settings=True
                )
                
                # Mark onboarding as completed
                onboarding.organizer = organizer
                onboarding.is_completed = True
                onboarding.save()
                
                # Return organizer data
                serializer = OrganizerSerializer(organizer)
                return Response(serializer.data)
                
        except Exception as e:
            return Response(
                {"detail": f"Error completing onboarding: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CurrentOrganizerView(RetrieveUpdateAPIView):
    """
    API view for retrieving and updating the organizer profile for the current user.
    """
    serializer_class = OrganizerSerializer
    permission_classes = [IsAuthenticated, IsOrganizer]

    def get_object(self):
        # The user is already authenticated, and IsOrganizer permission ensures they are an organizer.
        # We can now safely retrieve the organizer linked to the user.
        user = self.request.user
        if not hasattr(user, 'organizer') or not user.organizer:
            raise NotFound("No organizer is associated with the current user.")
        return user.organizer


class CheckSubdomainAvailabilityView(APIView):
    """
    Enterprise-grade subdomain availability checker.
    Public endpoint for pre-registration validation.
    """
    permission_classes = []  # Public endpoint - no authentication required
    
    def get(self, request):
        """
        Check if a subdomain is available.
        
        Query parameters:
        - slug: The subdomain to check
        
        Returns:
        - available: Boolean indicating if subdomain is available
        - message: Human-readable message
        - suggestions: List of alternative suggestions if not available
        """
        slug = request.query_params.get('slug', '').strip().lower()
        
        # Validation: Basic format check
        if not slug:
            return Response({
                'available': False,
                'message': 'El subdominio no puede estar vacío.',
                'suggestions': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validation: Length check
        if len(slug) < 3:
            return Response({
                'available': False,
                'message': 'El subdominio debe tener al menos 3 caracteres.',
                'suggestions': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(slug) > 50:
            return Response({
                'available': False,
                'message': 'El subdominio no puede tener más de 50 caracteres.',
                'suggestions': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validation: Format check (alphanumeric and hyphens only)
        if not re.match(r'^[a-z0-9-]+$', slug):
            return Response({
                'available': False,
                'message': 'El subdominio solo puede contener letras minúsculas, números y guiones.',
                'suggestions': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validation: Cannot start or end with hyphen
        if slug.startswith('-') or slug.endswith('-'):
            return Response({
                'available': False,
                'message': 'El subdominio no puede empezar o terminar con guión.',
                'suggestions': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validation: Cannot have consecutive hyphens
        if '--' in slug:
            return Response({
                'available': False,
                'message': 'El subdominio no puede tener guiones consecutivos.',
                'suggestions': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Reserved subdomain check
        reserved_slugs = [
            'admin', 'api', 'www', 'mail', 'ftp', 'localhost', 'test', 
            'dev', 'staging', 'prod', 'production', 'app', 'support',
            'help', 'docs', 'blog', 'news', 'status', 'dashboard',
            'panel', 'control', 'manage', 'system', 'root', 'user',
            'tuki', 'eventos', 'experiencias', 'alojamientos', 'tickets',
            'reservas', 'pagos', 'facturacion'
        ]
        
        if slug in reserved_slugs:
            return Response({
                'available': False,
                'message': f'"{slug}" es un subdominio reservado del sistema.',
                'suggestions': self._generate_suggestions(slug)
            })
        
        # Check if subdomain already exists
        existing_organizer = Organizer.objects.filter(slug=slug).first()
        existing_onboarding = OrganizerOnboarding.objects.filter(organization_slug=slug).first()
        
        if existing_organizer or existing_onboarding:
            return Response({
                'available': False,
                'message': f'El subdominio "{slug}" ya está en uso.',
                'suggestions': self._generate_suggestions(slug)
            })
        
        # Subdomain is available
        return Response({
            'available': True,
            'message': f'¡Perfecto! "{slug}" está disponible.',
            'suggestions': []
        })
    
    def _generate_suggestions(self, base_slug):
        """
        Generate alternative subdomain suggestions.
        """
        suggestions = []
        
        # Try with numbers
        for i in range(1, 6):
            suggestion = f"{base_slug}{i}"
            if not Organizer.objects.filter(slug=suggestion).exists() and \
               not OrganizerOnboarding.objects.filter(organization_slug=suggestion).exists():
                suggestions.append(suggestion)
        
        # Try with year
        from datetime import datetime
        year = datetime.now().year
        suggestion = f"{base_slug}{year}"
        if not Organizer.objects.filter(slug=suggestion).exists() and \
           not OrganizerOnboarding.objects.filter(organization_slug=suggestion).exists():
            suggestions.append(suggestion)
        
        # Try with 'official'
        suggestion = f"{base_slug}-oficial"
        if not Organizer.objects.filter(slug=suggestion).exists() and \
           not OrganizerOnboarding.objects.filter(organization_slug=suggestion).exists():
            suggestions.append(suggestion)
        
        return suggestions[:3]  # Return max 3 suggestions


class CheckEmailAvailabilityView(APIView):
    """
    Enterprise-grade email availability checker for onboarding.
    Public endpoint for pre-registration validation.
    """
    permission_classes = []  # Public endpoint - no authentication required
    
    def get(self, request):
        """
        Check if an email is available for registration.
        
        Query parameters:
        - email: The email to check
        
        Returns:
        - available: Boolean indicating if email is available
        - message: Human-readable message
        """
        email = request.query_params.get('email', '').strip().lower()
        
        # Validation: Basic format check
        if not email:
            return Response({
                'available': False,
                'message': 'El email no puede estar vacío.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validation: Email format check
        import re
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_pattern, email):
            return Response({
                'available': False,
                'message': 'El formato del email no es válido.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if email already exists in the system
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Check in existing users
        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            return Response({
                'available': False,
                'message': f'El email "{email}" ya está registrado en el sistema.'
            })
        
        # Check in onboarding data (pending registrations)
        existing_onboarding = OrganizerOnboarding.objects.filter(contact_email=email).first()
        if existing_onboarding:
            return Response({
                'available': False,
                'message': f'El email "{email}" ya está siendo usado en otro proceso de registro.'
            })
        
        # Email is available
        return Response({
            'available': True,
            'message': f'¡Perfecto! "{email}" está disponible.'
        }) 