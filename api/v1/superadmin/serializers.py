"""
Serializers for Super Admin JSON Experience Creation.
"""

from rest_framework import serializers
from django.utils.text import slugify
from datetime import datetime, timedelta
import logging

from apps.experiences.models import Experience
from apps.organizers.models import Organizer

logger = logging.getLogger(__name__)


class JsonExperienceCreateSerializer(serializers.Serializer):
    """
    🚀 ENTERPRISE: Serializer for creating experiences from JSON.
    
    Validates and normalizes JSON data for experience creation.
    Maps JSON fields to Experience model fields.
    """
    
    # Basic info
    title = serializers.CharField(max_length=255, required=True)
    slug = serializers.SlugField(required=False, allow_blank=True)
    description = serializers.CharField(required=True)
    short_description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=['draft', 'published', 'cancelled', 'completed'],
        default='draft'
    )
    type = serializers.ChoiceField(
        choices=['activity', 'tour', 'workshop', 'adventure', 'other'],
        default='activity'
    )
    
    # Organizer (will be set separately, but validate if provided)
    organizer = serializers.UUIDField(required=False)
    
    # Pricing
    price = serializers.DecimalField(max_digits=10, decimal_places=2, default=0, min_value=0)
    currency = serializers.CharField(max_length=3, default='CLP', required=False)
    is_free_tour = serializers.BooleanField(default=False)
    credit_per_person = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=0, allow_null=True
    )
    sales_cutoff_hours = serializers.IntegerField(default=2, min_value=1, max_value=24)
    
    # Precios para niños e infantes (opcional)
    child_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=0, allow_null=True
    )
    is_child_priced = serializers.BooleanField(default=False, required=False)
    infant_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=0, allow_null=True
    )
    is_infant_priced = serializers.BooleanField(default=False, required=False)
    
    # 🚀 ENTERPRISE: WhatsApp reservation (tours con reserva por WhatsApp - único flujo end-to-end funcional)
    is_whatsapp_reservation = serializers.BooleanField(
        default=False,
        help_text="Si es true, los usuarios reservan vía WhatsApp a Tuki (+56947884342) en lugar de pagar en la plataforma"
    )
    
    # Recurrence pattern
    recurrence_pattern = serializers.DictField(required=False, allow_null=True)
    
    # Location
    location_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    location_address = serializers.CharField(required=False, allow_blank=True)
    location_latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    location_longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    
    # Additional info (campos del flujo de WhatsApp)
    included = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    not_included = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    itinerary = serializers.ListField(
        child=serializers.DictField(), required=False, allow_empty=True
    )
    
    # Images (will be empty for JSON creation, se suben después)
    images = serializers.ListField(
        child=serializers.URLField(), required=False, allow_empty=True
    )
    
    # Optional fields
    booking_horizon_days = serializers.IntegerField(default=90, min_value=1)
    
    # Publication settings (pueden venir como objeto o parseados directamente)
    publication_settings = serializers.DictField(required=False, allow_null=True)
    
    # Date price overrides (Step 3 - opcional)
    date_price_overrides = serializers.ListField(
        child=serializers.DictField(), required=False, allow_empty=True
    )
    
    def validate_title(self, value):
        """Validate title is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("El título es requerido y no puede estar vacío.")
        return value.strip()
    
    def validate_description(self, value):
        """Validate description is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("La descripción es requerida y no puede estar vacía.")
        return value.strip()
    
    def validate_recurrence_pattern(self, value):
        """
        Validate recurrence pattern structure.
        Acepta el formato del flujo real: { schema_version: 1, weekly_schedule: {...} }
        """
        if not value:
            return value
        
        # Formato del flujo real: weekly_schedule
        if 'weekly_schedule' in value:
            weekly_schedule = value['weekly_schedule']
            if not isinstance(weekly_schedule, dict):
                raise serializers.ValidationError(
                    "El campo 'weekly_schedule' debe ser un objeto."
                )
            
            valid_days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
            for day, slots in weekly_schedule.items():
                if day.lower() not in valid_days:
                    raise serializers.ValidationError(
                        f"El día '{day}' no es válido. Debe ser uno de: {', '.join(valid_days)}."
                    )
                
                if not isinstance(slots, list):
                    raise serializers.ValidationError(
                        f"Los horarios para '{day}' deben ser un array."
                    )
                
                for slot_idx, slot in enumerate(slots):
                    if not isinstance(slot, dict):
                        raise serializers.ValidationError(
                            f"Cada slot en '{day}' debe ser un objeto."
                        )
                    
                    # Validar formato de tiempo si está presente
                    if 'startTime' in slot:
                        try:
                            datetime.strptime(slot['startTime'], '%H:%M')
                        except ValueError:
                            raise serializers.ValidationError(
                                f"El horario de inicio '{slot['startTime']}' en {day}[{slot_idx}] no está en formato válido (HH:mm)."
                            )
                    
                    if 'endTime' in slot:
                        try:
                            datetime.strptime(slot['endTime'], '%H:%M')
                        except ValueError:
                            raise serializers.ValidationError(
                                f"El horario de fin '{slot['endTime']}' en {day}[{slot_idx}] no está en formato válido (HH:mm)."
                            )
        
        # Formato legacy (mantener compatibilidad)
        elif 'pattern' in value:
            required_fields = ['pattern', 'times', 'days_of_week', 'start_date']
            for field in required_fields:
                if field not in value:
                    raise serializers.ValidationError(
                        f"El campo '{field}' es requerido en recurrence_pattern."
                    )
            
            if value['pattern'] not in ['daily', 'weekly', 'custom']:
                raise serializers.ValidationError(
                    "El patrón debe ser 'daily', 'weekly' o 'custom'."
                )
            
            if not isinstance(value['times'], list) or len(value['times']) == 0:
                raise serializers.ValidationError(
                    "El campo 'times' debe ser un array con al menos un horario."
                )
            
            for time_str in value['times']:
                try:
                    datetime.strptime(time_str, '%H:%M')
                except ValueError:
                    raise serializers.ValidationError(
                        f"El horario '{time_str}' no está en formato válido (HH:mm)."
                    )
        
        return value
    
    def validate_itinerary(self, value):
        """Validate itinerary items."""
        if not value:
            return value
        
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    "Cada item del itinerario debe ser un objeto."
                )
            
            if 'title' not in item or not item['title']:
                raise serializers.ValidationError(
                    "Cada item del itinerario debe tener un 'title'."
                )
            
            if 'description' not in item or not item['description']:
                raise serializers.ValidationError(
                    "Cada item del itinerario debe tener una 'description'."
                )
            
            # Validate time format if provided
            if 'time' in item and item['time']:
                try:
                    datetime.strptime(item['time'], '%H:%M')
                except ValueError:
                    raise serializers.ValidationError(
                        f"El horario '{item['time']}' no está en formato válido (HH:mm)."
                    )
        
        return value
    
    def validate_organizer(self, value):
        """Validate organizer exists and has experience module enabled."""
        if not value:
            return value
        
        try:
            organizer = Organizer.objects.get(id=value)
            if not organizer.has_experience_module:
                raise serializers.ValidationError(
                    f"El organizador '{organizer.name}' no tiene el módulo de experiencias habilitado."
                )
            return value
        except Organizer.DoesNotExist:
            raise serializers.ValidationError(
                f"El organizador con ID '{value}' no existe."
            )
    
    def validate(self, attrs):
        """Cross-field validation."""
        errors = {}
        
        # Validate free tour requirements (solo si es free_tour, no para WhatsApp)
        is_free_tour = attrs.get('is_free_tour', False)
        is_whatsapp = attrs.get('is_whatsapp_reservation', False)
        
        if is_free_tour and not is_whatsapp:
            credit_per_person = attrs.get('credit_per_person')
            if credit_per_person is None or credit_per_person <= 0:
                errors['credit_per_person'] = [
                    "El crédito por persona es requerido para tours gratuitos y debe ser mayor a 0."
                ]
        
        # Para WhatsApp, is_free_tour debe ser false
        if is_whatsapp and is_free_tour:
            errors['is_free_tour'] = [
                "Los tours con reserva por WhatsApp no pueden ser free_tour."
            ]
        
        if errors:
            raise serializers.ValidationError(errors)
        
        return attrs
    
    def _parse_duration_to_days(self, duration_str):
        """Parse duration string to days (matching frontend logic)."""
        if not duration_str:
            return 90
        v = duration_str.lower()
        if '1 mes' in v:
            return 30
        if '3 mes' in v:
            return 90
        if '6 mes' in v:
            return 180
        if '1 año' in v or '1 a\u00f1o' in v:
            return 365
        if 'indef' in v:
            return 365
        return 90
    
    def _parse_sales_cutoff_to_hours(self, sales_cutoff_str):
        """Parse sales cutoff string to hours (matching frontend logic)."""
        if not sales_cutoff_str:
            return 1
        v = sales_cutoff_str.lower()
        if '2 hora' in v:
            return 2
        if '4 hora' in v:
            return 4
        if '1 d\u00eda' in v or '1 dia' in v:
            return 24
        if '2 d\u00edas' in v or '2 dias' in v:
            return 48
        return 1
    
    def create(self, validated_data):
        """
        Create experience from validated JSON data.
        Note: organizer should be set separately before calling this.
        """
        # Process publication_settings if provided
        publication_settings = validated_data.pop('publication_settings', None)
        if publication_settings:
            if 'booking_horizon_days' not in validated_data:
                duration = publication_settings.get('duration')
                if duration:
                    validated_data['booking_horizon_days'] = self._parse_duration_to_days(duration)
            
            if 'sales_cutoff_hours' not in validated_data:
                sales_cutoff = publication_settings.get('salesCutoff')
                if sales_cutoff:
                    validated_data['sales_cutoff_hours'] = self._parse_sales_cutoff_to_hours(sales_cutoff)
        
        # Extract date_price_overrides (se crearán después)
        date_price_overrides = validated_data.pop('date_price_overrides', [])
        
        # Generate slug if not provided
        if 'slug' not in validated_data or not validated_data['slug']:
            validated_data['slug'] = slugify(validated_data['title'])
            # Ensure unique slug
            base_slug = validated_data['slug']
            counter = 1
            while Experience.objects.filter(slug=validated_data['slug']).exists():
                validated_data['slug'] = f"{base_slug}-{counter}"
                counter += 1
        
        # Set default values for lists if not provided (campos del flujo de WhatsApp)
        if 'included' not in validated_data:
            validated_data['included'] = []
        if 'not_included' not in validated_data:
            validated_data['not_included'] = []
        if 'itinerary' not in validated_data:
            validated_data['itinerary'] = []
        if 'images' not in validated_data:
            validated_data['images'] = []
        if 'recurrence_pattern' not in validated_data:
            validated_data['recurrence_pattern'] = {}
        
        # Set defaults for WhatsApp tours
        if validated_data.get('is_whatsapp_reservation'):
            validated_data['is_free_tour'] = False
            validated_data['type'] = 'tour'
            if 'status' not in validated_data:
                validated_data['status'] = 'published'
        
        # Set defaults
        if 'booking_horizon_days' not in validated_data:
            validated_data['booking_horizon_days'] = 90
        if 'sales_cutoff_hours' not in validated_data:
            validated_data['sales_cutoff_hours'] = 2
        
        # Create experience
        experience = Experience.objects.create(**validated_data)
        
        logger.info(
            f"✅ [JSON_EXPERIENCE_CREATE] Experience '{experience.title}' created from JSON (ID: {experience.id})"
        )
        
        return experience

