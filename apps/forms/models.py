from django.db import models
from apps.users.models import User
from apps.organizers.models import Organizer

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
