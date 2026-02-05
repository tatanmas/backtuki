"""
SuperAdmin Experiences Views
Endpoints para creación de experiencias desde JSON.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db import transaction
import logging

from apps.experiences.models import Experience
from apps.experiences.utils import generate_tour_instances_from_pattern
from apps.organizers.models import Organizer

from ..permissions import IsSuperUser
from ..serializers import JsonExperienceCreateSerializer

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def create_experience_from_json(request):
    """
    🚀 ENTERPRISE: Create experience from JSON data.
    
    POST /api/v1/superadmin/experiences/create-from-json/
    
    Body:
        {
            "experience_data": { ... },  # JSON experience data
            "organizer_id": "uuid"      # Organizer ID to link the experience
        }
    
    Returns:
        {
            "id": "experience-uuid",
            "title": "...",
            "instances_created": 42,
            ...
        }
    """
    try:
        experience_data = request.data.get('experience_data')
        organizer_id = request.data.get('organizer_id')
        
        if not experience_data:
            return Response(
                {"detail": "El campo 'experience_data' es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not organizer_id:
            return Response(
                {"detail": "El campo 'organizer_id' es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate organizer exists and has experience module
        from apps.organizers.models import Organizer
        try:
            organizer = Organizer.objects.get(id=organizer_id)
            if not organizer.has_experience_module:
                return Response(
                    {
                        "detail": f"El organizador '{organizer.name}' no tiene el módulo de experiencias habilitado."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Organizer.DoesNotExist:
            return Response(
                {"detail": f"El organizador con ID '{organizer_id}' no existe."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate and normalize JSON data
        serializer = JsonExperienceCreateSerializer(data=experience_data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create experience
        with transaction.atomic():
            validated_data = serializer.validated_data
            validated_data['organizer'] = organizer
            
            # Extract date_price_overrides from experience_data (no se validan en serializer)
            date_price_overrides = experience_data.get('date_price_overrides', [])
            
            # Create experience using the serializer's create method
            experience = serializer.create(validated_data)
            
            # Generate tour instances from recurrence pattern
            instances_created = 0
            if experience.recurrence_pattern:
                instances_created = generate_tour_instances_from_pattern(experience)
            
            # Create date price overrides (Step 3 - opcional)
            # Step3 permite configurarlos para paid o WhatsApp, pero CreateTourPage solo los crea si isPaid
            # Para el flujo de WhatsApp (end-to-end funcional), también los creamos si están presentes
            overrides_created = 0
            if date_price_overrides and len(date_price_overrides) > 0:
                # Solo crear si es WhatsApp (flujo end-to-end funcional) o paid
                if experience.is_whatsapp_reservation or (not experience.is_free_tour and not experience.is_whatsapp_reservation):
                    from apps.experiences.models import ExperienceDatePriceOverride
                    from datetime import datetime as dt
                    
                    for override_data in date_price_overrides:
                        try:
                            # Parse date
                            override_date = dt.strptime(override_data['date'], '%Y-%m-%d').date()
                            
                            # Parse times if provided
                            start_time = None
                            end_time = None
                            if override_data.get('start_time'):
                                start_time = dt.strptime(override_data['start_time'], '%H:%M').time()
                            if override_data.get('end_time'):
                                end_time = dt.strptime(override_data['end_time'], '%H:%M').time()
                            
                            ExperienceDatePriceOverride.objects.create(
                                experience=experience,
                                date=override_date,
                                start_time=start_time,
                                end_time=end_time,
                                override_adult_price=override_data.get('override_adult_price'),
                                override_child_price=override_data.get('override_child_price'),
                                override_infant_price=override_data.get('override_infant_price'),
                            )
                            overrides_created += 1
                        except (ValueError, KeyError) as e:
                            logger.warning(
                                f"⚠️ [JSON_EXPERIENCE_CREATE] Error creating date price override: {e}"
                            )
                            continue
            
            # Serialize response
            from apps.experiences.serializers import ExperienceSerializer
            response_serializer = ExperienceSerializer(experience)
            
            response_data = response_serializer.data
            response_data['instances_created'] = instances_created
            response_data['overrides_created'] = overrides_created
            
            logger.info(
                f"✅ [JSON_EXPERIENCE_CREATE] Experience '{experience.title}' created from JSON "
                f"(ID: {experience.id}, Organizer: {organizer.name}, "
                f"Instances: {instances_created}, Overrides: {overrides_created})"
            )
            
            return Response(response_data, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(
            f"🔴 [JSON_EXPERIENCE_CREATE] Error creating experience from JSON: {str(e)}",
            exc_info=True
        )
        return Response(
            {
                "detail": f"Error al crear la experiencia: {str(e)}",
                "error_type": type(e).__name__
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def update_experience_commission(request, experience_id):
    """
    TUKI Creators: Update platform fee rate and creator commission rate for an experience.
    
    PATCH /api/v1/superadmin/experiences/<experience_id>/commission/
    
    Body:
        {
            "platform_service_fee_rate": 0.15 | null,  // 0.15 = 15%
            "creator_commission_rate": 0.5 | null     // 0.5 = 50% of platform fee
        }
    """
    try:
        experience = Experience.objects.get(id=experience_id)
    except Experience.DoesNotExist:
        return Response(
            {"detail": "Experiencia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )
    
    platform_rate = request.data.get('platform_service_fee_rate')
    creator_rate = request.data.get('creator_commission_rate')
    
    if platform_rate is not None:
        try:
            from decimal import Decimal
            r = Decimal(str(platform_rate))
            if r < 0 or r > 1:
                return Response(
                    {"detail": "platform_service_fee_rate debe estar entre 0 y 1."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            experience.platform_service_fee_rate = r
        except (TypeError, ValueError):
            return Response(
                {"detail": "platform_service_fee_rate debe ser un número."},
                status=status.HTTP_400_BAD_REQUEST
            )
    elif 'platform_service_fee_rate' in request.data:
        experience.platform_service_fee_rate = None
    
    if creator_rate is not None:
        try:
            from decimal import Decimal
            r = Decimal(str(creator_rate))
            if r < 0 or r > 1:
                return Response(
                    {"detail": "creator_commission_rate debe estar entre 0 y 1."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            experience.creator_commission_rate = r
        except (TypeError, ValueError):
            return Response(
                {"detail": "creator_commission_rate debe ser un número."},
                status=status.HTTP_400_BAD_REQUEST
            )
    elif 'creator_commission_rate' in request.data:
        experience.creator_commission_rate = None
    
    experience.save(update_fields=['platform_service_fee_rate', 'creator_commission_rate', 'updated_at'])
    
    return Response({
        "id": str(experience.id),
        "title": experience.title,
        "platform_service_fee_rate": float(experience.platform_service_fee_rate) if experience.platform_service_fee_rate is not None else None,
        "creator_commission_rate": float(experience.creator_commission_rate) if experience.creator_commission_rate is not None else None,
    }, status=status.HTTP_200_OK)
