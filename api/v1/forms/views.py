from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.forms.models import Form
from apps.forms.serializers import FormSerializer
from apps.organizers.models import OrganizerUser

class FormViewSet(viewsets.ModelViewSet):
    """
    API endpoint for forms - this is a proxy to the tenant app
    """
    serializer_class = FormSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return forms for the current organizer"""
        try:
            # Handle anonymous users
            if not self.request.user.is_authenticated:
                return Form.objects.none()
                
            # Get the user's organizer through OrganizerUser relationship
            organizer_user = OrganizerUser.objects.filter(user=self.request.user).first()
            
            if organizer_user and organizer_user.organizer:
                return Form.objects.filter(organizer=organizer_user.organizer)
            else:
                # Return empty queryset if user is not linked to an organizer
                return Form.objects.none()
        except Exception as e:
            # Log the error and return empty queryset
            print(f"Error in get_queryset for FormViewSet: {e}")
            return Form.objects.none()
    
    def perform_create(self, serializer):
        # Get the user's organizer through OrganizerUser relationship
        organizer_user = OrganizerUser.objects.filter(user=self.request.user).first()
        
        if organizer_user and organizer_user.organizer:
            serializer.save(
                organizer=organizer_user.organizer,
                created_by=self.request.user
            )
        else:
            # Return error if user is not an organizer
            raise ValueError("User is not associated with an organizer")
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get only active forms"""
        try:
            forms = self.get_queryset().filter(status='active')
            serializer = self.get_serializer(forms, many=True)
            return Response(serializer.data)
        except Exception as e:
            # Log the error and return an appropriate response
            print(f"Error in active forms endpoint: {e}")
            return Response(
                {"detail": "Unable to retrieve active forms."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """Toggle form status between active and inactive"""
        form = self.get_object()
        
        if form.status == 'active':
            form.status = 'inactive'
        else:
            form.status = 'active'
            
        form.save()
        serializer = self.get_serializer(form)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """
        Pass the duplication request to the apps.forms viewset
        """
        # Import the forms app duplicate view
        from apps.forms.views import FormViewSet as TenantFormViewSet
        
        # Create a temporary viewset instance
        tenant_viewset = TenantFormViewSet()
        tenant_viewset.request = request
        tenant_viewset.kwargs = {'pk': pk}
        
        # Call the duplicate action method
        return tenant_viewset.duplicate(request, pk=pk) 