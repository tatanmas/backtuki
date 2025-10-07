from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.organizers.models import Organizer
from core.utils import get_upload_path

class Form(models.Model):
    """Model for a form template created by an organizer."""
    FORM_STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('draft', 'Draft'),
    )
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    organizer = models.ForeignKey(Organizer, on_delete=models.CASCADE, related_name='form_templates')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_forms')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=FORM_STATUS_CHOICES, default='active')
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return self.name

class FormField(models.Model):
    """Model for a field within a form."""
    FIELD_TYPE_CHOICES = (
        ('text', 'Text'),
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('number', 'Number'),
        ('select', 'Select'),
        ('checkbox', 'Checkbox'),
        ('radio', 'Radio'),
        ('date', 'Date'),
        ('textarea', 'Textarea'),
        ('heading', 'Heading'),
        ('paragraph', 'Paragraph'),
        # 🚀 ENTERPRISE: New field types for robust data collection
        ('file', 'File Upload'),
        ('image', 'Image Upload'),
        ('url', 'URL'),
        ('time', 'Time'),
        ('datetime', 'Date & Time'),
        ('rating', 'Rating (1-5)'),
        ('slider', 'Slider'),
        ('multi_select', 'Multiple Select'),
        ('signature', 'Digital Signature'),
    )
    
    FIELD_WIDTH_CHOICES = (
        ('full', 'Full Width'),
        ('half', 'Half Width'),
        ('third', 'Third Width'),
    )
    
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='fields')
    label = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES)
    required = models.BooleanField(default=False)
    placeholder = models.CharField(max_length=255, blank=True, null=True)
    help_text = models.TextField(blank=True, null=True)
    default_value = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    width = models.CharField(max_length=10, choices=FIELD_WIDTH_CHOICES, default='full')
    
    # 🚀 ENTERPRISE: File upload configuration
    max_file_size = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        help_text="Maximum file size in MB (for file/image fields)"
    )
    allowed_file_types = models.TextField(
        blank=True, 
        null=True,
        help_text="Comma-separated list of allowed file extensions (e.g., 'pdf,doc,docx')"
    )
    
    # 🚀 ENTERPRISE: Additional field configuration
    min_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    step_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # 🚀 ENTERPRISE: Multi-select and conditional logic
    allow_multiple = models.BooleanField(default=False, help_text="Allow multiple selections")
    show_other_option = models.BooleanField(default=False, help_text="Show 'Other' option with text input")
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.form.name} - {self.label}"

class FieldOption(models.Model):
    """Model for options for select, checkbox, and radio fields."""
    field = models.ForeignKey(FormField, on_delete=models.CASCADE, related_name='options')
    label = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.label

class FieldValidation(models.Model):
    """Model for field validation rules."""
    VALIDATION_TYPE_CHOICES = (
        ('required', 'Required'),
        ('min_length', 'Minimum Length'),
        ('max_length', 'Maximum Length'),
        ('min_value', 'Minimum Value'),
        ('max_value', 'Maximum Value'),
        ('pattern', 'Pattern/Regex'),
        ('email', 'Email Format'),
    )
    
    field = models.ForeignKey(FormField, on_delete=models.CASCADE, related_name='validations')
    type = models.CharField(max_length=20, choices=VALIDATION_TYPE_CHOICES)
    value = models.CharField(max_length=255, blank=True, null=True)
    message = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"{self.field.label} - {self.type}"

class ConditionalLogic(models.Model):
    """Model for conditional display logic for fields."""
    CONDITION_TYPE_CHOICES = (
        ('equals', 'Equals'),
        ('not_equals', 'Not Equals'),
        ('contains', 'Contains'),
        ('not_contains', 'Not Contains'),
        ('greater_than', 'Greater Than'),
        ('less_than', 'Less Than'),
    )
    
    field = models.ForeignKey(FormField, on_delete=models.CASCADE, related_name='conditional_logic')
    source_field = models.ForeignKey(FormField, on_delete=models.CASCADE, related_name='target_logic')
    condition = models.CharField(max_length=20, choices=CONDITION_TYPE_CHOICES)
    value = models.CharField(max_length=255)
    
    def __str__(self):
        return f"{self.field.label} depends on {self.source_field.label}"


# 🚀 ENTERPRISE: Form Response Storage System
class FormResponse(models.Model):
    """Model to store form responses from ticket purchases."""
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='responses')
    ticket = models.OneToOneField(
        'events.Ticket', 
        on_delete=models.CASCADE, 
        related_name='form_response',
        null=True,
        blank=True
    )
    
    # Basic info
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    # Response data (JSON for simple fields)
    response_data = models.JSONField(default=dict, help_text="Simple field responses")
    
    class Meta:
        ordering = ['-submitted_at']
    
    def __str__(self):
        ticket_info = f" (Ticket: {self.ticket.ticket_number})" if self.ticket else ""
        return f"Response to {self.form.name}{ticket_info}"


class FormResponseFile(models.Model):
    """Model to store file uploads from form responses."""
    response = models.ForeignKey(FormResponse, on_delete=models.CASCADE, related_name='files')
    field = models.ForeignKey(FormField, on_delete=models.CASCADE)
    
    # File storage
    file = models.FileField(upload_to=get_upload_path)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    content_type = models.CharField(max_length=100)
    
    # Metadata
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.original_filename} for {self.field.label}"
    
    @property
    def file_size_mb(self):
        """Return file size in MB."""
        return round(self.file_size / (1024 * 1024), 2)
    
    def get_download_url(self):
        """Get secure download URL for the file."""
        if self.file:
            return self.file.url
        return None
