from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from django.core.files.storage import default_storage
from django.conf import settings
from apps.forms.models import Form, FormResponse, FormResponseFile
from apps.forms.serializers import FormSerializer, FormResponseSerializer
from apps.events.models import Ticket
from apps.organizers.models import OrganizerUser
import os
import uuid
from core.utils import get_upload_path


class FormResponseViewSet(viewsets.ModelViewSet):
    """🚀 ENTERPRISE: ViewSet for handling form responses with file uploads."""
    serializer_class = FormResponseSerializer
    
    def get_queryset(self):
        return FormResponse.objects.all()
    
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_file(self, request):
        """
        🚀 ENTERPRISE: Upload file for form field.
        This endpoint handles file uploads during form submission.
        """
        if 'file' not in request.FILES:
            return Response({'detail': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        file_obj = request.FILES['file']
        field_id = request.data.get('field_id')
        ticket_id = request.data.get('ticket_id')
        
        if not field_id:
            return Response({'detail': 'field_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Validate field exists and get form
            from apps.forms.models import FormField
            field = FormField.objects.get(id=field_id)
            
            # Validate file size if specified
            if field.max_file_size and file_obj.size > field.max_file_size * 1024 * 1024:
                return Response({
                    'detail': f'File too large. Maximum {field.max_file_size}MB allowed.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate file type if specified
            if field.allowed_file_types:
                allowed_types = [t.strip().lower() for t in field.allowed_file_types.split(',')]
                file_extension = file_obj.name.split('.')[-1].lower()
                if file_extension not in allowed_types:
                    return Response({
                        'detail': f'File type not allowed. Allowed types: {field.allowed_file_types}'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate unique filename
            filename = f"{uuid.uuid4().hex}.{file_obj.name.split('.')[-1]}"
            
            # Create directory path for form files
            upload_path = f"form_responses/{field.form.id}/{field.id}"
            file_path = os.path.join(settings.MEDIA_ROOT, upload_path, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save file
            with open(file_path, 'wb+') as destination:
                for chunk in file_obj.chunks():
                    destination.write(chunk)
            
            # Create or get form response
            form_response = None
            if ticket_id:
                try:
                    ticket = Ticket.objects.get(id=ticket_id)
                    form_response, created = FormResponse.objects.get_or_create(
                        form=field.form,
                        ticket=ticket,
                        defaults={
                            'ip_address': self.get_client_ip(request),
                            'user_agent': request.META.get('HTTP_USER_AGENT', '')
                        }
                    )
                except Ticket.DoesNotExist:
                    pass
            
            if not form_response:
                # Create temporary response (will be linked to ticket later)
                form_response = FormResponse.objects.create(
                    form=field.form,
                    ip_address=self.get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            
            # Create file record
            response_file = FormResponseFile.objects.create(
                response=form_response,
                field=field,
                file=f"{upload_path}/{filename}",
                original_filename=file_obj.name,
                file_size=file_obj.size,
                content_type=file_obj.content_type or 'application/octet-stream'
            )
            
            # Return file URL
            file_url = f"{settings.MEDIA_URL}{upload_path}/{filename}"
            
            return Response({
                'file_id': response_file.id,
                'file_url': file_url,
                'original_filename': file_obj.name,
                'file_size': response_file.file_size_mb,
                'response_id': form_response.id
            }, status=status.HTTP_201_CREATED)
            
        except FormField.DoesNotExist:
            return Response({'detail': 'Form field not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # Clean up file if it was created
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            
            return Response({
                'detail': f'File upload failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def submit_response(self, request, pk=None):
        """
        🚀 ENTERPRISE: Submit complete form response.
        Links all uploaded files and form data to a ticket.
        """
        try:
            form_response = self.get_object()
            ticket_id = request.data.get('ticket_id')
            response_data = request.data.get('response_data', {})
            
            if ticket_id:
                ticket = Ticket.objects.get(id=ticket_id)
                form_response.ticket = ticket
            
            # Update response data
            form_response.response_data = response_data
            form_response.save()
            
            return Response({
                'detail': 'Form response submitted successfully',
                'response_id': form_response.id
            })
            
        except Ticket.DoesNotExist:
            return Response({'detail': 'Ticket not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'detail': f'Submission failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class FormViewSet(viewsets.ModelViewSet):
    """🚀 ENTERPRISE: Enhanced form management with response tracking."""
    serializer_class = FormSerializer
    permission_classes = [IsAuthenticated]
    
    def get_organizer(self):
        """Obtener el organizador asociado al usuario actual."""
        try:
            # Handle anonymous users
            if not self.request.user.is_authenticated:
                return None
            
            # Buscar OrganizerUser, si hay múltiples tomar el más reciente
            organizer_users = OrganizerUser.objects.filter(user=self.request.user)
            if organizer_users.exists():
                organizer_user = organizer_users.order_by('-created_at').first()
                return organizer_user.organizer
            else:
                return None
        except Exception as e:
            print(f"[FormViewSet] Error getting organizer: {e}")
            return None
    
    def get_queryset(self):
        # Filter by organizer if authenticated
        organizer = self.get_organizer()
        if organizer:
            return Form.objects.filter(organizer=organizer)
        return Form.objects.none()
    
    def perform_create(self, serializer):
        """🚀 ENTERPRISE: Auto-assign organizer and created_by when creating forms."""
        print(f"[FormViewSet] perform_create called for user: {self.request.user}")
        print(f"[FormViewSet] User authenticated: {self.request.user.is_authenticated}")
        
        organizer = self.get_organizer()
        print(f"[FormViewSet] Found organizer: {organizer}")
        
        if not organizer:
            print(f"[FormViewSet] ERROR: No organizer found for user {self.request.user}")
            raise ValueError("No organizer found for current user")
        
        print(f"[FormViewSet] Saving form with organizer: {organizer} and created_by: {self.request.user}")
        serializer.save(
            organizer=organizer,
            created_by=self.request.user
        )
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get only active forms for the current organizer."""
        organizer = self.get_organizer()
        if not organizer:
            return Response([])
        
        active_forms = Form.objects.filter(
            organizer=organizer,
            status='active'
        ).order_by('-updated_at')
        
        serializer = self.get_serializer(active_forms, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def responses(self, request, pk=None):
        """Get all responses for a form."""
        form = self.get_object()
        responses = FormResponse.objects.filter(form=form).select_related('ticket')
        
        response_data = []
        for response in responses:
            files = []
            for file_obj in response.files.all():
                files.append({
                    'field_id': file_obj.field.id,
                    'field_label': file_obj.field.label,
                    'filename': file_obj.original_filename,
                    'file_size_mb': file_obj.file_size_mb,
                    'download_url': file_obj.get_download_url(),
                    'uploaded_at': file_obj.uploaded_at
                })
            
            response_data.append({
                'id': response.id,
                'ticket_number': response.ticket.ticket_number if response.ticket else None,
                'attendee_name': f"{response.ticket.first_name} {response.ticket.last_name}" if response.ticket else "Unknown",
                'submitted_at': response.submitted_at,
                'response_data': response.response_data,
                'files': files
            })
        
        return Response(response_data)
    
    @action(detail=True, methods=['get'])
    def export_responses(self, request, pk=None):
        """Export form responses as CSV."""
        form = self.get_object()
        # TODO: Implement CSV export functionality
        return Response({'detail': 'CSV export not yet implemented'})