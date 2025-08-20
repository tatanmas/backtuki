from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction

from .models import Form, FormField
from .serializers import FormSerializer, FormFieldSerializer
from apps.organizers.models import OrganizerUser

class IsOrganizerUser(permissions.BasePermission):
    """
    Custom permission to only allow users from the current organization.
    """
    def has_permission(self, request, view):
        # Check if the user is authenticated and is a member of the organization
        if not request.user.is_authenticated:
            return False
            
        # Check if the user is associated with an organizer through OrganizerUser
        try:
            organizer_user = OrganizerUser.objects.get(user=request.user)
            return organizer_user.organizer is not None
        except OrganizerUser.DoesNotExist:
            return False

class FormViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows form templates to be viewed or edited.
    """
    queryset = Form.objects.all()
    serializer_class = FormSerializer
    permission_classes = [IsOrganizerUser]
    
    def get_queryset(self):
        """
        This view should return a list of all forms
        for the currently authenticated user's organization.
        """
        return Form.objects.filter(organizer=self.request.user.organizer)
    
    def perform_create(self, serializer):
        serializer.save(
            organizer=self.request.user.organizer,
            created_by=self.request.user
        )
    
    @action(detail=True, methods=['get'])
    def fields(self, request, pk=None):
        """
        Get all fields for a specific form.
        """
        form = self.get_object()
        fields = form.fields.all()
        serializer = FormFieldSerializer(fields, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """
        Get all active forms.
        """
        forms = self.get_queryset().filter(status='active')
        serializer = self.get_serializer(forms, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """
        Duplicate a form including all its fields, options, validations, and logic.
        """
        original_form = self.get_object()
        
        with transaction.atomic():
            # Create a copy of the form
            new_form = Form.objects.create(
                name=f"Copy of {original_form.name}",
                description=original_form.description,
                organizer=self.request.user.organizer,
                created_by=self.request.user,
                status=original_form.status
            )
            
            # Copy all fields and related data
            for field in original_form.fields.all():
                # Create a copy of the field
                new_field = FormField.objects.create(
                    form=new_form,
                    label=field.label,
                    type=field.type,
                    required=field.required,
                    placeholder=field.placeholder,
                    help_text=field.help_text,
                    default_value=field.default_value,
                    order=field.order,
                    width=field.width
                )
                
                # Copy options
                for option in field.options.all():
                    new_field.options.create(
                        label=option.label,
                        value=option.value,
                        order=option.order
                    )
                
                # Copy validations
                for validation in field.validations.all():
                    new_field.validations.create(
                        type=validation.type,
                        value=validation.value,
                        message=validation.message
                    )
            
            # Handle conditional logic in a second pass
            field_mapping = {}
            for old_field in original_form.fields.all():
                new_field = new_form.fields.get(label=old_field.label, order=old_field.order)
                field_mapping[old_field.id] = new_field
            
            # Now create conditional logic using the field mapping
            for old_field in original_form.fields.all():
                for logic in old_field.conditional_logic.all():
                    new_field = field_mapping[old_field.id]
                    new_source_field = field_mapping[logic.source_field.id]
                    
                    new_field.conditional_logic.create(
                        source_field=new_source_field,
                        condition=logic.condition,
                        value=logic.value
                    )
        
        serializer = self.get_serializer(new_form)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """
        Toggle the active status of a form.
        """
        form = self.get_object()
        
        if form.status == 'active':
            form.status = 'inactive'
        else:
            form.status = 'active'
            
        form.save()
        serializer = self.get_serializer(form)
        return Response(serializer.data)
