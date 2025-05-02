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
    OrganizerOnboarding,
    BillingDetails,
    BankingDetails,
)
from .serializers import (
    OrganizerSerializer,
    OrganizerDetailSerializer,
    OrganizerUserSerializer,
    OrganizerSubscriptionSerializer,
    OrganizerOnboardingSerializer,
    BillingDetailsSerializer,
    BankingDetailsSerializer,
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
        if self.action in ['list', 'retrieve', 'current']:
            return [permissions.AllowAny()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsSuperAdmin()]
        return [permissions.IsAuthenticated(), IsOrganizer()]
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def current(self, request):
        """
        Return the authenticated user's organizer information.
        This endpoint can be accessed without authentication for frontend validations.
        """
        # Para usuarios no autenticados o sin token válido
        if not request.user.is_authenticated:
            return Response(
                {"detail": "User is not authenticated."},
                status=status.HTTP_200_OK
            )
        
        # Para usuarios autenticados pero sin organizador asociado
        if not hasattr(request.user, 'organizer_roles') or not request.user.organizer_roles.exists():
            return Response(
                {"detail": "User does not have any associated organizer."},
                status=status.HTTP_200_OK  # Cambiado de 404 a 200 para mejor manejo frontend
            )
        
        # Obtener el primer organizador asociado con el usuario
        # En el futuro, podríamos manejar múltiples organizadores por usuario de manera diferente
        organizer_role = request.user.organizer_roles.first()
        organizer = organizer_role.organizer
        
        serializer = OrganizerDetailSerializer(organizer, context={'request': request})
        
        # Añadir la información del rol del usuario a la respuesta
        data = serializer.data
        data['user_role'] = {
            'is_admin': organizer_role.is_admin,
            'can_manage_events': organizer_role.can_manage_events,
            'can_manage_accommodations': organizer_role.can_manage_accommodations,
            'can_manage_experiences': organizer_role.can_manage_experiences,
            'can_view_reports': organizer_role.can_view_reports,
            'can_manage_settings': organizer_role.can_manage_settings,
        }
        
        return Response(data)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsOrganizer])
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
    
    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsOrganizer])
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
    
    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsOrganizer])
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
    
    @action(detail=True, methods=['get', 'put', 'patch'], permission_classes=[permissions.IsAuthenticated, IsOrganizer])
    def billing_details(self, request, pk=None):
        """
        Get or update billing details for an organizer.
        """
        organizer = self.get_object()
        
        # Check if user belongs to this organizer
        if not request.user.organizer_roles.filter(organizer=organizer, can_manage_settings=True).exists():
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if request.method == 'GET':
            try:
                billing = organizer.billing_details
                serializer = BillingDetailsSerializer(billing)
                return Response(serializer.data)
            except BillingDetails.DoesNotExist:
                return Response(
                    {"detail": "Billing details not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # For PUT and PATCH
        try:
            billing = organizer.billing_details
            serializer = BillingDetailsSerializer(billing, data=request.data, partial=request.method == 'PATCH')
        except BillingDetails.DoesNotExist:
            # Create new billing details
            serializer = BillingDetailsSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(organizer=organizer)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get', 'put', 'patch'], permission_classes=[permissions.IsAuthenticated, IsOrganizer])
    def banking_details(self, request, pk=None):
        """
        Get or update banking details for an organizer.
        """
        organizer = self.get_object()
        
        # Check if user belongs to this organizer
        if not request.user.organizer_roles.filter(organizer=organizer, can_manage_settings=True).exists():
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if request.method == 'GET':
            try:
                banking = organizer.banking_details
                serializer = BankingDetailsSerializer(banking)
                return Response(serializer.data)
            except BankingDetails.DoesNotExist:
                return Response(
                    {"detail": "Banking details not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # For PUT and PATCH
        try:
            banking = organizer.banking_details
            serializer = BankingDetailsSerializer(banking, data=request.data, partial=request.method == 'PATCH')
        except BankingDetails.DoesNotExist:
            # Create new banking details
            serializer = BankingDetailsSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(organizer=organizer)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrganizerOnboardingViewSet(viewsets.ModelViewSet):
    """
    API endpoint for organizer onboarding.
    """
    serializer_class = OrganizerOnboardingSerializer
    
    # Temporarily allow all access for development
    # TODO: Revert this to proper authentication for production
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        """
        Get queryset based on permission.
        """
        # For development, allow access to all onboarding data
        # TODO: Restrict this properly in production
        return OrganizerOnboarding.objects.all()
    
    def perform_create(self, serializer):
        """Create a new onboarding entry."""
        # For development, create a default organizer if it doesn't exist
        from apps.organizers.models import Organizer
        from django_tenants.utils import schema_context
        
        # Try to get an existing organizer, or create a default one
        try:
            # Switch to public schema to create tenant
            with schema_context('public'):
                organizer = Organizer.objects.first()
                if not organizer:
                    # Create a default organizer for development
                    organizer = Organizer.objects.create(
                        name="Development Organizer",
                        slug="development",
                        contact_email="dev@example.com",
                        schema_name="development",
                    )
                    print(f"Created default organizer: {organizer.name}")
                
                serializer.save(organizer=organizer)
        except Exception as e:
            print(f"Error creating onboarding: {e}")
            raise
    
    def perform_update(self, serializer):
        """
        Override perform_update to ensure tenant operations are performed in the correct schema.
        """
        from django_tenants.utils import schema_context
        
        with schema_context('public'):
            serializer.save()
    
    def update(self, request, *args, **kwargs):
        """
        Override the update method to ensure it's performed in the correct schema.
        """
        from django_tenants.utils import schema_context
        
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        with schema_context('public'):
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        
        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def save_step(self, request):
        """
        Save a specific step of the onboarding process.
        """
        from django_tenants.utils import schema_context
        
        step = request.data.get('step')
        data = request.data.get('data', {})
        
        if not step or not isinstance(data, dict):
            return Response(
                {"detail": "Invalid request. 'step' and 'data' are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from apps.organizers.models import Organizer
            
            # Get or create onboarding for the organization based on data
            onboarding = None
            organizer = None
            
            # Ensure we're in the public schema for tenant operations
            with schema_context('public'):
                # For step 1, we'll create a temporary organizer
                if step == 1:
                    # Create a temporary organizer or find existing
                    temp_organizer = Organizer.objects.filter(schema_name='temp_onboarding').first()
                    if not temp_organizer:
                        temp_organizer = Organizer.objects.create(
                            name="Temporary Onboarding",
                            slug="temp_onboarding",
                            contact_email="temp@example.com",
                            schema_name="temp_onboarding",
                        )
                    onboarding, created = OrganizerOnboarding.objects.get_or_create(organizer=temp_organizer)
                
                # For step 2, we'll update or create the actual organizer
                elif step == 2 and 'organizationName' in data and 'organizationSlug' in data:
                    # Check if we can find existing onboarding
                    existing_onboarding = OrganizerOnboarding.objects.filter(completed_step__gte=1).order_by('-updated_at').first()
                    
                    # Generate a valid schema name from slug
                    import re
                    schema_name = re.sub(r'[^a-z0-9]', '', data['organizationSlug'].lower())
                    if not schema_name:
                        schema_name = 'org' + str(hash(data['organizationName']))[:8]
                    
                    # Check if organizer with this schema name already exists
                    if Organizer.objects.filter(schema_name=schema_name).exists():
                        # Append a number to make it unique
                        base_schema = schema_name
                        counter = 1
                        while Organizer.objects.filter(schema_name=schema_name).exists():
                            schema_name = f"{base_schema}{counter}"
                            counter += 1
                    
                    # Create the actual organizer for this onboarding
                    organizer = Organizer.objects.create(
                        name=data['organizationName'],
                        slug=data['organizationSlug'],
                        contact_email="onboarding@example.com",  # Will be updated in step 3
                        schema_name=schema_name,
                    )
                    
                    # If we had a previous onboarding, transfer the data to the new organizer
                    if existing_onboarding:
                        onboarding = OrganizerOnboarding.objects.create(
                            organizer=organizer,
                            selected_types=existing_onboarding.selected_types,
                            completed_step=1  # We're now on step 2
                        )
                    else:
                        onboarding = OrganizerOnboarding.objects.create(organizer=organizer)
                
                # For step 3, find the organizer from step 2
                elif step == 3:
                    # Find the most recently updated onboarding from step 2
                    onboarding = OrganizerOnboarding.objects.filter(completed_step__gte=2).order_by('-updated_at').first()
                    if not onboarding:
                        return Response(
                            {"detail": "No previous onboarding found. Please complete step 2 first."},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    organizer = onboarding.organizer
                    
                    # Update the organizer email if provided
                    if 'contactEmail' in data:
                        organizer.contact_email = data['contactEmail']
                        organizer.save()
                
                # If we don't have an onboarding by now, something went wrong
                if not onboarding:
                    return Response(
                        {"detail": "Could not find or create onboarding entry."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Now process the step data
                if step == 1:  # Module selection
                    if 'selectedTypes' in data:
                        onboarding.selected_types = data['selectedTypes']
                    onboarding.completed_step = max(onboarding.completed_step, 1)
                    
                elif step == 2:  # Organization information
                    if 'organizationName' in data:
                        onboarding.organization_name = data['organizationName']
                    if 'organizationSlug' in data:
                        onboarding.organization_slug = data['organizationSlug']
                    if 'organizationSize' in data:
                        onboarding.organization_size = data['organizationSize']
                    
                    onboarding.completed_step = max(onboarding.completed_step, 2)
                    
                elif step == 3:  # Representative information
                    if 'contactName' in data:
                        onboarding.contact_name = data['contactName']
                    if 'contactEmail' in data:
                        onboarding.contact_email = data['contactEmail']
                    if 'contactPhone' in data:
                        onboarding.contact_phone = data['contactPhone']
                        
                    # Module-specific fields
                    if 'hasExperience' in data:
                        onboarding.has_experience = data['hasExperience']
                    if 'experienceYears' in data:
                        onboarding.experience_years = data['experienceYears']
                    if 'eventSize' in data:
                        onboarding.event_size = data['eventSize']
                    if 'experienceType' in data:
                        onboarding.experience_type = data['experienceType']
                    if 'experienceFrequency' in data:
                        onboarding.experience_frequency = data['experienceFrequency']
                    if 'accommodationType' in data:
                        onboarding.accommodation_type = data['accommodationType']
                    if 'accommodationCapacity' in data:
                        onboarding.accommodation_capacity = data['accommodationCapacity']
                    
                    onboarding.completed_step = max(onboarding.completed_step, 3)
                    onboarding.is_completed = True
                    
                    # Enable modules based on selected types
                    if organizer:
                        selected_types = onboarding.selected_types or []
                        organizer.has_events_module = 'eventos' in selected_types
                        organizer.has_accommodation_module = 'alojamiento' in selected_types
                        organizer.has_experience_module = 'experiencias' in selected_types
                        organizer.save()
                    
                onboarding.save()
                
                return Response(OrganizerOnboardingSerializer(onboarding).data)
        except Exception as e:
            print(f"Error in save_step: {e}")
            return Response({
                "error": str(e),
                "detail": "Unable to save onboarding data"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def current(self, request):
        """
        Get the current onboarding for the user.
        """
        # Try to find the most recent active onboarding
        from django_tenants.utils import schema_context

        try:
            # Ensure we're in the public schema for tenant operations
            with schema_context('public'):
                onboarding = OrganizerOnboarding.objects.filter(is_completed=False).order_by('-updated_at').first()
                if onboarding:
                    return Response(OrganizerOnboardingSerializer(onboarding).data)
                
                # If no active onboarding found, create a new one
                from apps.organizers.models import Organizer
                temp_organizer = Organizer.objects.filter(schema_name='temp_onboarding').first()
                if not temp_organizer:
                    temp_organizer = Organizer.objects.create(
                        name="Temporary Onboarding",
                        slug="temp_onboarding",
                        contact_email="temp@example.com",
                        schema_name="temp_onboarding",
                    )
                
                onboarding, created = OrganizerOnboarding.objects.get_or_create(organizer=temp_organizer)
                return Response(OrganizerOnboardingSerializer(onboarding).data)
                
        except Exception as e:
            print(f"Error in current onboarding: {e}")
            return Response({
                "error": str(e),
                "detail": "Unable to get or create onboarding data"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 