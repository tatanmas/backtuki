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


def validate_itinerary_items(value):
    """
    Validate itinerary items (shared by Experience and Erasmus activity).
    `time` is optional and accepts:
    - HH:mm (e.g. "10:00") for clock time
    - Step number as string or int (e.g. "1", "2", 3) for "Paso 1", "Paso 2"
    - Any other string as label (e.g. "Inicio", "Primera hora", "Segunda hora")
    So one itinerary works for all instances/slots regardless of start time.
    """
    if not value:
        return
    for item in value:
        if not isinstance(item, dict):
            raise serializers.ValidationError(
                "Cada item del itinerario debe ser un objeto."
            )
        if "title" not in item or not item["title"]:
            raise serializers.ValidationError(
                "Cada item del itinerario debe tener un 'title'."
            )
        if "description" not in item or not item["description"]:
            raise serializers.ValidationError(
                "Cada item del itinerario debe tener una 'description'."
            )
        if "time" in item and item["time"] is not None and item["time"] != "":
            t = item["time"]
            if isinstance(t, int):
                if not (1 <= t <= 99):
                    raise serializers.ValidationError(
                        f"El paso del itinerario '{t}' debe ser un número entre 1 y 99."
                    )
            else:
                tstr = str(t).strip()
                if ":" in tstr:
                    try:
                        datetime.strptime(tstr, "%H:%M")
                    except ValueError:
                        raise serializers.ValidationError(
                            f"El horario '{tstr}' no está en formato válido (HH:mm)."
                        )
                elif tstr.isdigit():
                    if not (1 <= int(tstr) <= 99):
                        raise serializers.ValidationError(
                            f"El paso del itinerario '{tstr}' debe ser entre 1 y 99."
                        )


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
    
    # Duration (optional)
    duration_minutes = serializers.IntegerField(
        required=False, allow_null=True, min_value=1,
        help_text="Duración en minutos"
    )

    # Capacity (optional; used as default for instances when slot does not set capacity/maxCapacity)
    max_participants = serializers.IntegerField(
        required=False, allow_null=True, min_value=1,
        help_text="Máximo de participantes por instancia (null = ilimitado)"
    )
    min_participants = serializers.IntegerField(
        required=False, allow_null=True, min_value=1,
        default=1,
        help_text="Mínimo de participantes para realizar el tour"
    )

    # Carga: when experience is under Tuki organizer, real operator identifier for future transfer
    managed_operator_slug = serializers.CharField(
        max_length=100, required=False, allow_blank=True,
        help_text="Real operator slug when managed by Tuki (e.g. molantours)"
    )

    # Payment model (DB has NOT NULL; migration 0011)
    payment_model = serializers.ChoiceField(
        choices=[('full_upfront', 'Full upfront'), ('deposit_only', 'Deposit only')],
        default='full_upfront',
        required=False,
    )

    # Optional fields
    booking_horizon_days = serializers.IntegerField(default=90, min_value=1)
    
    # Publication settings (pueden venir como objeto o parseados directamente)
    publication_settings = serializers.DictField(required=False, allow_null=True)
    
    # Date price overrides (Step 3 - opcional)
    date_price_overrides = serializers.ListField(
        child=serializers.DictField(), required=False, allow_empty=True
    )

    # Imported reviews (Google, GetYourGuide, etc.) - created in view after experience
    reviews = serializers.ListField(
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
        Por cada día acepta array de slots O un solo objeto (se normaliza a array de 1).
        Así se soportan múltiples horarios por día (varios slots en el array).
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
            # Normalizar: cada día debe quedar como list de slots (copiamos para no mutar input)
            normalized = {}
            for day, slots in weekly_schedule.items():
                if day.lower() not in valid_days:
                    raise serializers.ValidationError(
                        f"El día '{day}' no es válido. Debe ser uno de: {', '.join(valid_days)}."
                    )
                # Aceptar array de slots O un solo objeto → siempre guardar como array
                if isinstance(slots, list):
                    slot_list = slots
                elif isinstance(slots, dict):
                    slot_list = [slots]
                else:
                    raise serializers.ValidationError(
                        f"Los horarios para '{day}' deben ser un array o un objeto con startTime/endTime."
                    )
                normalized[day] = slot_list
                
                for slot_idx, slot in enumerate(slot_list):
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
            value = {**value, 'weekly_schedule': normalized}
        
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
        """Validate itinerary items (HH:mm, paso 1-99, or label)."""
        validate_itinerary_items(value)
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
        
        # Validate free tour requirements: credit_per_person required when is_free_tour (with or without WhatsApp)
        is_free_tour = attrs.get('is_free_tour', False)
        is_whatsapp = attrs.get('is_whatsapp_reservation', False)
        
        if is_free_tour:
            credit_per_person = attrs.get('credit_per_person')
            if credit_per_person is None or credit_per_person <= 0:
                errors['credit_per_person'] = [
                    "El crédito por persona es requerido para free tours y debe ser mayor a 0."
                ]
        
        # Free tour + reserva WhatsApp is allowed (same flow: reserve via WhatsApp, no payment on platform)
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
        # Extract reviews (imported reviews se crean en la vista)
        validated_data.pop('reviews', None)
        
        # Slug: usar el pasado o generar desde título (Experience.slug max_length=50)
        if 'slug' not in validated_data or not (validated_data.get('slug') or '').strip():
            raw_slug = slugify(validated_data['title'])
            base_slug = raw_slug[:47] if len(raw_slug) > 47 else raw_slug
        else:
            base_slug = slugify(validated_data['slug'].strip())[:47]
        validated_data['slug'] = base_slug
        counter = 1
        while Experience.objects.filter(slug=validated_data['slug']).exists():
            validated_data['slug'] = (f"{base_slug}-{counter}")[:50]
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
        
        # Set defaults for WhatsApp-only (non-free) tours
        if validated_data.get('is_whatsapp_reservation') and not validated_data.get('is_free_tour'):
            validated_data['type'] = 'tour'
            if 'status' not in validated_data:
                validated_data['status'] = 'published'
        
        # Set defaults
        if 'booking_horizon_days' not in validated_data:
            validated_data['booking_horizon_days'] = 90
        if 'sales_cutoff_hours' not in validated_data:
            validated_data['sales_cutoff_hours'] = 2
        # DB has NOT NULL on payment_model (migration 0011); never pass None
        if validated_data.get('payment_model') is None:
            validated_data['payment_model'] = 'full_upfront'
        
        # Create experience
        experience = Experience.objects.create(**validated_data)
        
        logger.info(
            f"✅ [JSON_EXPERIENCE_CREATE] Experience '{experience.title}' created from JSON (ID: {experience.id})"
        )
        
        return experience


class JsonAccommodationCreateSerializer(serializers.Serializer):
    """Serializer for creating Accommodation from JSON (create-from-json flow). organizer_id is optional (superadmin-owned)."""

    organizer_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=255, required=True)
    slug = serializers.SlugField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    short_description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=["draft", "published", "cancelled"],
        default="draft",
        required=False,
    )
    property_type = serializers.ChoiceField(
        choices=["cabin", "house", "apartment", "hotel", "hostel", "villa", "other"],
        default="cabin",
        required=False,
    )
    location_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    location_address = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    country = serializers.CharField(max_length=255, default="Chile", required=False)
    city = serializers.CharField(max_length=255, required=False, allow_blank=True)
    guests = serializers.IntegerField(default=2, min_value=1, required=False)
    bedrooms = serializers.IntegerField(default=1, min_value=0, required=False)
    # Legacy: "bathrooms" (int or float e.g. 4.5 → 4 full + 1 half). Preferred: full_bathrooms + half_bathrooms (industry standard).
    bathrooms = serializers.FloatField(default=1, min_value=0, required=False)
    full_bathrooms = serializers.IntegerField(default=1, min_value=0, required=False)
    half_bathrooms = serializers.IntegerField(default=0, min_value=0, required=False)
    beds = serializers.IntegerField(default=1, min_value=0, required=False, allow_null=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, default=0, min_value=0, required=False)
    currency = serializers.CharField(max_length=3, default="CLP", required=False)
    amenities = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)
    not_amenities = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)
    images = serializers.ListField(child=serializers.URLField(), required=False, allow_empty=True)
    gallery_media_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True)
    # Rental hub / unit (for centrales de arrendamiento)
    rental_hub_id = serializers.UUIDField(required=False, allow_null=True)
    # Hotel / room (habitaciones con herencia)
    hotel_id = serializers.UUIDField(required=False, allow_null=True)
    inherit_location_from_hotel = serializers.BooleanField(default=True, required=False)
    inherit_amenities_from_hotel = serializers.BooleanField(default=True, required=False)
    room_type_code = serializers.CharField(max_length=30, required=False, allow_blank=True)
    external_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    unit_type = serializers.CharField(max_length=30, required=False, allow_blank=True)
    tower = serializers.CharField(max_length=30, required=False, allow_blank=True)
    floor = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    unit_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    square_meters = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True, min_value=0)
    min_nights = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Minimum number of nights for a booking. Overrides hub/hotel rule when set.",
    )
    # Número de orden (opcional). public_code se genera al publicar; no enviar en JSON.
    display_order = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Order number from 1. Optional; assigned automatically when published if omitted.",
    )
    # Prefijo opcional del código público (ej. Tuki-PV → Tuki-PV-001). Si se omite, se usa tuqui{N}-{random}.
    public_code_prefix = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        help_text="Optional prefix for public code (e.g. Tuki-PV for Pedra Verde → Tuki-PV-001).",
    )

    # Reseñas (igual que alojamientos normales; aplica también a unidades de central de arrendamiento)
    reviews = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        help_text="Array de reseñas: author_name, rating (1-5), text o body, review_date (YYYY-MM-DD), author_location, stay_type, host_reply",
    )
    rating_avg = serializers.FloatField(
        min_value=1, max_value=5,
        required=False, allow_null=True,
        help_text="Promedio 1-5 (opcional). Se acepta ej. 4.93 y se guarda redondeado a 1 decimal (4.9). Si envías reviews, se recalcula.",
    )
    review_count = serializers.IntegerField(min_value=0, required=False, allow_null=True)

    # Cobros adicionales (v1.5): code, name, charge_type (per_stay|per_night), amount, is_optional, default_quantity, max_quantity, display_order
    extra_charges = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        help_text="Array de cobros: code (único), name, description (opcional), charge_type (per_stay|per_night), amount (>=0), currency (opcional), is_optional (bool), default_quantity (>=1), max_quantity (opcional), display_order (>=0).",
    )


class JsonCarRentalCompanyCreateSerializer(serializers.Serializer):
    """Serializer for creating CarRentalCompany from JSON. organizer_id optional."""

    organizer_id = serializers.UUIDField(required=False, allow_null=True)
    name = serializers.CharField(max_length=255, required=True)
    slug = serializers.SlugField(required=False, allow_blank=True)
    short_description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    hero_media_id = serializers.UUIDField(required=False, allow_null=True)
    gallery_media_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True)
    conditions = serializers.JSONField(required=False, default=dict)
    is_active = serializers.BooleanField(default=True, required=False)
    country = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=255, required=False, allow_blank=True)


class JsonCarCreateSerializer(serializers.Serializer):
    """Serializer for creating Car from JSON. company_id required."""

    company_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=255, required=True)
    slug = serializers.SlugField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    short_description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=["draft", "published", "cancelled"], default="draft", required=False)
    price_per_day = serializers.DecimalField(max_digits=12, decimal_places=2, default=0, min_value=0, required=False)
    currency = serializers.CharField(max_length=3, default="CLP", required=False)
    pickup_time_default = serializers.CharField(max_length=5, required=False, allow_blank=True)
    return_time_default = serializers.CharField(max_length=5, required=False, allow_blank=True)
    included = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)
    not_included = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)
    inherit_company_conditions = serializers.BooleanField(default=True, required=False)
    conditions_override = serializers.JSONField(required=False, default=dict)
    gallery_media_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True)
    images = serializers.ListField(child=serializers.URLField(), required=False, allow_empty=True)
    min_driver_age = serializers.IntegerField(required=False, allow_null=True, min_value=18)
    transmission = serializers.ChoiceField(choices=["manual", "automatic"], default="manual", required=False)
    seats = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    bags = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class JsonDestinationCreateSerializer(serializers.Serializer):
    """Serializer for creating LandingDestination from JSON (create-from-json flow)."""

    name = serializers.CharField(max_length=255, required=True)
    slug = serializers.SlugField(max_length=255, required=True)
    country = serializers.CharField(max_length=255, default="Chile", required=False)
    region = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    hero_image = serializers.URLField(max_length=500, required=False, allow_blank=True)
    hero_media_id = serializers.UUIDField(required=False, allow_null=True)
    gallery_media_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    is_active = serializers.BooleanField(default=True, required=False)
    images = serializers.ListField(child=serializers.URLField(), required=False, allow_empty=True)
    travel_guides = serializers.ListField(required=False, allow_empty=True)
    transportation = serializers.ListField(required=False, allow_empty=True)
    accommodation_ids = serializers.ListField(required=False, allow_empty=True)
    experience_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True)
    event_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True)
    featured_type = serializers.ChoiceField(
        choices=["experience", "event", "accommodation"],
        required=False,
        allow_null=True,
    )
    featured_id = serializers.UUIDField(required=False, allow_null=True)


class JsonErasmusTimelineItemSerializer(serializers.Serializer):
    """Serializer for creating ErasmusTimelineItem from JSON."""

    title_es = serializers.CharField(max_length=255, required=True)
    title_en = serializers.CharField(max_length=255, required=False, allow_blank=True)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    image = serializers.URLField(max_length=500, required=False, allow_blank=True)
    scheduled_date = serializers.DateField(required=False, allow_null=True)
    display_order = serializers.IntegerField(default=0, min_value=0, required=False)
    experience_id = serializers.UUIDField(required=False, allow_null=True)
    is_active = serializers.BooleanField(default=True, required=False)


class JsonErasmusActivityInstanceSerializer(serializers.Serializer):
    """One instance in create-from-json or bulk instances."""

    scheduled_date = serializers.DateField(required=False, allow_null=True)
    scheduled_month = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=12)
    scheduled_year = serializers.IntegerField(required=False, allow_null=True)
    scheduled_label_es = serializers.CharField(max_length=100, required=False, allow_blank=True)
    scheduled_label_en = serializers.CharField(max_length=100, required=False, allow_blank=True)
    start_time = serializers.CharField(max_length=8, required=False, allow_blank=True, allow_null=True)  # HH:MM or HH:MM:SS
    end_time = serializers.CharField(max_length=8, required=False, allow_blank=True, allow_null=True)
    display_order = serializers.IntegerField(default=0, min_value=0, required=False)
    is_active = serializers.BooleanField(default=True, required=False)
    instructions_es = serializers.CharField(required=False, allow_blank=True)
    instructions_en = serializers.CharField(required=False, allow_blank=True)
    whatsapp_message_es = serializers.CharField(required=False, allow_blank=True)
    whatsapp_message_en = serializers.CharField(required=False, allow_blank=True)
    interested_count_boost = serializers.IntegerField(default=0, min_value=0, required=False)

    def validate(self, attrs):
        has_date = attrs.get("scheduled_date") is not None
        has_month_year = (
            attrs.get("scheduled_month") is not None or attrs.get("scheduled_year") is not None
        )
        has_labels = bool(
            (attrs.get("scheduled_label_es") or "").strip() or (attrs.get("scheduled_label_en") or "").strip()
        )
        if not (has_date or has_month_year or has_labels):
            raise serializers.ValidationError(
                "Set either scheduled_date, or scheduled_month/scheduled_year, or scheduled_label_es/en."
            )
        return attrs


class JsonErasmusActivityCreateSerializer(serializers.Serializer):
    """Activity data for create-from-json (same structure as Experience: itinerary, meeting point, included/not_included)."""

    title_es = serializers.CharField(max_length=255, required=True)
    title_en = serializers.CharField(max_length=255, required=False, allow_blank=True)
    slug = serializers.SlugField(max_length=255, required=True)
    description_es = serializers.CharField(required=False, allow_blank=True)
    description_en = serializers.CharField(required=False, allow_blank=True)
    short_description_es = serializers.CharField(max_length=500, required=False, allow_blank=True)
    short_description_en = serializers.CharField(max_length=500, required=False, allow_blank=True)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    location_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    location_address = serializers.CharField(required=False, allow_blank=True)
    duration_minutes = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    included = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        allow_empty=True,
    )
    not_included = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        allow_empty=True,
    )
    itinerary = serializers.ListField(
        required=False,
        allow_empty=True,
        child=serializers.DictField(allow_empty=True),
    )
    images = serializers.ListField(
        child=serializers.URLField(max_length=500, allow_blank=True),
        required=False,
        allow_empty=True,
    )
    display_order = serializers.IntegerField(default=0, min_value=0, required=False)
    is_active = serializers.BooleanField(default=True, required=False)
    experience_id = serializers.UUIDField(required=False, allow_null=True)
    detail_layout = serializers.ChoiceField(
        choices=["default", "two_column"],
        default="default",
        required=False,
    )
    is_paid = serializers.BooleanField(default=False, required=False)
    price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0,
    )

    def validate_itinerary(self, value):
        """Same flexibility as Experience: time = HH:mm, step 1-99, or any label (e.g. Primera hora, Segunda hora)."""
        validate_itinerary_items(value)
        return value

