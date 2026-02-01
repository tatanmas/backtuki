"""
Utilidades comunes para el sistema de migración.
"""

import hashlib
import os
from django.apps import apps
from django.core.files.base import ContentFile
from django.db import connection


def get_all_models_in_order():
    """
    Retorna todos los modelos de la aplicación en orden de dependencias.
    
    Orden: modelos sin ForeignKey primero, luego modelos que dependen de ellos.
    """
    # Orden manual basado en dependencias conocidas
    MODEL_ORDER = [
        # Core y base
        'users.User',
        'core.Country',
        'core.Location',
        
        # Organizers
        'organizers.Organizer',
        'organizers.OrganizerOnboarding',
        'organizers.BillingDetails',
        'organizers.BankingDetails',
        'organizers.OrganizerUser',
        'organizers.OrganizerSubscription',
        'organizers.StudentCenterConfig',
        
        # Events
        'events.EventCategory',
        'events.Event',
        'events.EventImage',
        'events.TicketCategory',
        'events.TicketTier',
        'events.Order',
        'events.OrderItem',
        'events.Ticket',
        'events.ComplimentaryTicketInvitation',
        'events.TicketNote',
        'events.TicketHolderReservation',
        'events.TicketHold',
        'events.Coupon',
        'events.CouponHold',
        'events.EventCommunication',
        'events.EmailLog',
        'events.SimpleBooking',
        'events.TicketRequest',
        
        # Forms
        'forms.Form',
        'forms.FormField',
        'forms.FormResponse',
        'forms.FormResponseFile',
        
        # Experiences
        'experiences.Experience',
        'experiences.TimeSlot',
        'experiences.ExperienceReservation',
        
        # Accommodations
        'accommodations.Accommodation',
        
        # Payments
        'payments.Payment',
        'payments.PaymentMethod',
        
        # Satisfaction
        'satisfaction.SatisfactionSurvey',
        'satisfaction.SatisfactionSurveySubmission',
        
        # WhatsApp
        'whatsapp.TourOperator',
        'whatsapp.WhatsAppSession',
        'whatsapp.WhatsAppMessage',
        
        # Terminal (si existe)
        'terminal.TerminalRoute',
        'terminal.TerminalSchedule',
        'terminal.TerminalBooking',
    ]
    
    # Filtrar solo modelos que existen
    existing_models = []
    for model_path in MODEL_ORDER:
        try:
            app_label, model_name = model_path.split('.')
            model = apps.get_model(app_label, model_name)
            existing_models.append(model_path)
        except LookupError:
            # Modelo no existe, skip
            pass
    
    return existing_models


def find_all_file_fields():
    """
    Encuentra todos los ImageField y FileField en todos los modelos.
    
    Returns:
        List of tuples: [(Model, field_name), ...]
    """
    file_fields = []
    
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if hasattr(field, 'upload_to'):
                # Es un FileField o ImageField
                file_fields.append((model, field.name))
    
    return file_fields


def calculate_file_checksum(file_field, algorithm='md5'):
    """
    Calcula el checksum de un archivo.
    
    Args:
        file_field: FileField o ImageField
        algorithm: 'md5' o 'sha256'
        
    Returns:
        str: Checksum en formato hexadecimal, None si el archivo no existe
    """
    if not file_field:
        return None
    
    try:
        # Verificar si el archivo existe físicamente antes de intentar abrirlo
        from django.core.files.storage import default_storage
        if not default_storage.exists(file_field.name):
            return None
        
        if algorithm == 'md5':
            hasher = hashlib.md5()
        elif algorithm == 'sha256':
            hasher = hashlib.sha256()
        else:
            raise ValueError(f"Algoritmo no soportado: {algorithm}")
        
        # Leer archivo en chunks para no cargar todo en memoria
        file_field.open('rb')
        for chunk in file_field.chunks(chunk_size=8192):
            hasher.update(chunk)
        file_field.close()
        
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error calculando checksum: {e}")
        return None


def get_database_version():
    """
    Obtiene la versión de la base de datos.
    
    Returns:
        str: Versión de PostgreSQL
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        # Extraer solo "PostgreSQL 14.x"
        if 'PostgreSQL' in version:
            parts = version.split(',')[0]
            return parts
        return version


def get_serializer_for_model(model):
    """
    Obtiene el serializer apropiado para un modelo.
    
    Intenta usar serializers existentes en api/v1/, si no existe
    usa un serializer genérico.
    
    Args:
        model: Django model class
        
    Returns:
        Serializer class
    """
    from rest_framework import serializers
    
    app_label = model._meta.app_label
    model_name = model._meta.object_name
    
    # Intentar importar serializer existente
    try:
        # Patrón común: api.v1.{app_label}.serializers.{ModelName}Serializer
        module_path = f"api.v1.{app_label}.serializers"
        module = __import__(module_path, fromlist=[f"{model_name}Serializer"])
        serializer_class = getattr(module, f"{model_name}Serializer", None)
        
        if serializer_class:
            return serializer_class
    except (ImportError, AttributeError):
        pass
    
    # Si no existe, crear serializer genérico
    class GenericModelSerializer(serializers.ModelSerializer):
        class Meta:
            model_class = model
            fields = '__all__'
    
    GenericModelSerializer.Meta.model = model
    return GenericModelSerializer


def format_file_size(size_bytes):
    """
    Formatea tamaño de archivo en formato legible.
    
    Args:
        size_bytes: Tamaño en bytes
        
    Returns:
        str: Tamaño formateado (ej: "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def sanitize_filename(filename):
    """
    Sanitiza nombre de archivo para evitar path traversal.
    
    Args:
        filename: Nombre de archivo
        
    Returns:
        str: Nombre sanitizado
    """
    # Remover path components
    filename = os.path.basename(filename)
    # Remover caracteres peligrosos
    dangerous_chars = ['..', '/', '\\', '\x00']
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    return filename
