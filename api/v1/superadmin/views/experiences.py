"""
SuperAdmin Experiences Views
Endpoints para creación de experiencias desde JSON y administración de free tours
(instancias, bloqueo por fecha, inscritos, regenerar instancias).
"""

from datetime import datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
import logging

from apps.experiences.models import (
    Experience,
    ExperienceImportedReview,
    TourInstance,
    TourBooking,
)
from apps.experiences.utils import generate_tour_instances_from_pattern
from apps.experiences.serializers import (
    ExperienceSerializer,
    TourInstanceSerializer,
    TourBookingSerializer,
)
from apps.organizers.models import Organizer

from ..permissions import IsSuperUser
from ..serializers import JsonExperienceCreateSerializer
from apps.landing_destinations.models import LandingDestination, LandingDestinationExperience

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

            # Create imported reviews (from experience_data, not from serializer validated_data)
            reviews_data = experience_data.get('reviews') or []
            reviews_created = 0
            if isinstance(reviews_data, list) and len(reviews_data) > 0:
                from datetime import datetime as dt
                for item in reviews_data[:100]:
                    if not isinstance(item, dict):
                        continue
                    author_name = (item.get('author_name') or item.get('author') or '').strip()
                    if not author_name:
                        continue
                    try:
                        rating = int(item.get('rating', 5))
                        rating = max(1, min(5, rating))
                    except (TypeError, ValueError):
                        rating = 5
                    body = (item.get('body') or item.get('text') or '').strip()
                    review_date = None
                    if item.get('review_date'):
                        try:
                            review_date = dt.strptime(str(item['review_date'])[:10], '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            pass
                    source = (item.get('source') or '')[:50]
                    ExperienceImportedReview.objects.create(
                        experience=experience,
                        author_name=author_name[:255],
                        rating=rating,
                        body=body,
                        review_date=review_date,
                        source=source,
                    )
                    reviews_created += 1
                if reviews_created:
                    logger.info(
                        f"✅ [JSON_EXPERIENCE_CREATE] Created {reviews_created} imported review(s) for '{experience.title}'"
                    )
            
            # Serialize response
            from apps.experiences.serializers import ExperienceSerializer
            response_serializer = ExperienceSerializer(experience)
            
            response_data = response_serializer.data
            response_data['instances_created'] = instances_created
            response_data['overrides_created'] = overrides_created
            response_data['reviews_created'] = reviews_created

            logger.info(
                f"✅ [JSON_EXPERIENCE_CREATE] Experience '{experience.title}' created from JSON "
                f"(ID: {experience.id}, Organizer: {organizer.name}, "
                f"Instances: {instances_created}, Overrides: {overrides_created}, Reviews: {reviews_created})"
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
            "creator_commission_rate": 0.5 | null,    // 0.5 = 50% of base; 0.06 = 6% if basis=pct_total
            "creator_commission_basis": "pct_tuki_commission" | "pct_total"  // default: pct_tuki_commission
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
    creator_basis = request.data.get('creator_commission_basis')
    
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

    if creator_basis in ('pct_tuki_commission', 'pct_total'):
        experience.creator_commission_basis = creator_basis

    update_fields = ['platform_service_fee_rate', 'creator_commission_rate', 'updated_at']
    if creator_basis is not None:
        update_fields.append('creator_commission_basis')
    experience.save(update_fields=update_fields)

    return Response({
        "id": str(experience.id),
        "title": experience.title,
        "platform_service_fee_rate": float(experience.platform_service_fee_rate) if experience.platform_service_fee_rate is not None else None,
        "creator_commission_rate": float(experience.creator_commission_rate) if experience.creator_commission_rate is not None else None,
        "creator_commission_basis": experience.creator_commission_basis,
    }, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def superadmin_experience_detail(request, experience_id):
    """
    PATCH /api/v1/superadmin/experiences/<experience_id>/
    Update experience fields and optionally organizer_id.
    """
    try:
        experience = Experience.objects.get(id=experience_id)
    except Experience.DoesNotExist:
        return Response(
            {"detail": "Experiencia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    data = request.data
    # Allow updating organizer
    organizer_id = data.get('organizer_id')
    if organizer_id is not None:
        if organizer_id == '' or organizer_id is None:
            return Response(
                {"detail": "organizer_id no puede ser nulo (experiencias requieren organizador)."},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            organizer = Organizer.objects.get(id=organizer_id)
            if not organizer.has_experience_module:
                return Response(
                    {"detail": f"El organizador '{organizer.name}' no tiene el módulo de experiencias."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            experience.organizer = organizer
        except Organizer.DoesNotExist:
            return Response(
                {"detail": "Organizador no encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )

    # Allowed fields for PATCH (same as ExperienceSerializer minus read_only)
    allowed = {
        'title', 'slug', 'description', 'short_description', 'status', 'type',
        'pricing_mode', 'price', 'child_price', 'is_child_priced', 'infant_price', 'is_infant_priced',
        'currency', 'is_free_tour', 'credit_per_person', 'capacity_count_rule',
        'booking_horizon_days', 'sales_cutoff_hours', 'recurrence_pattern',
        'location_name', 'location_address', 'location_latitude', 'location_longitude',
        'country', 'duration_minutes', 'max_participants', 'min_participants',
        'included', 'not_included', 'requirements', 'itinerary', 'images', 'categories', 'tags',
        'is_active', 'notify_whatsapp_group_on_booking',
    }
    for key in allowed:
        if key in data:
            setattr(experience, key, data[key])

    experience.save()
    serializer = ExperienceSerializer(experience)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT'])
@permission_classes([IsSuperUser])
def experience_landing_destinations(request, experience_id):
    """
    GET: list landing destinations that include this experience.
    PUT: set which landing destinations include this experience. Body: { "destination_ids": ["uuid", ...] }.
    """
    try:
        experience = Experience.objects.get(id=experience_id)
    except Experience.DoesNotExist:
        return Response(
            {"detail": "Experiencia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == 'GET':
        dests = LandingDestination.objects.filter(
            destination_experiences__experience_id=experience_id
        ).order_by('name').values('id', 'name', 'slug')
        return Response([
            {"id": str(d["id"]), "name": d["name"], "slug": d["slug"]}
            for d in dests
        ], status=status.HTTP_200_OK)

    # PUT
    destination_ids = request.data.get("destination_ids")
    if not isinstance(destination_ids, list):
        return Response(
            {"detail": "Se requiere 'destination_ids' (lista de UUIDs de destinos)."},
            status=status.HTTP_400_BAD_REQUEST
        )
    exp_id_str = str(experience.id)
    with transaction.atomic():
        LandingDestinationExperience.objects.filter(experience_id=exp_id_str).delete()
        for i, dest_id in enumerate(destination_ids):
            try:
                dest = LandingDestination.objects.get(id=dest_id)
            except (LandingDestination.DoesNotExist, ValueError, TypeError):
                continue
            LandingDestinationExperience.objects.create(
                destination=dest,
                experience_id=exp_id_str,
                order=i,
            )
    dests = LandingDestination.objects.filter(
        destination_experiences__experience_id=experience_id
    ).order_by('name').values('id', 'name', 'slug')
    return Response([
        {"id": str(d["id"]), "name": d["name"], "slug": d["slug"]}
        for d in dests
    ], status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def superadmin_experience_instances(request, experience_id):
    """
    GET /api/v1/superadmin/experiences/<experience_id>/instances/
    List tour instances for an experience. Query: date_from, date_to, status.
    """
    try:
        experience = Experience.objects.get(id=experience_id)
    except Experience.DoesNotExist:
        return Response(
            {"detail": "Experiencia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    qs = TourInstance.objects.filter(experience=experience).select_related('experience').order_by('start_datetime')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    status_filter = request.query_params.get('status')
    if date_from:
        try:
            d = datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(start_datetime__date__gte=d)
        except ValueError:
            pass
    if date_to:
        try:
            d = datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(start_datetime__date__lte=d)
        except ValueError:
            pass
    if status_filter and status_filter in ('active', 'blocked', 'cancelled'):
        qs = qs.filter(status=status_filter)

    serializer = TourInstanceSerializer(qs, many=True)
    return Response({"results": serializer.data})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def superadmin_experience_instances_block_by_date(request, experience_id):
    """
    POST /api/v1/superadmin/experiences/<experience_id>/instances/block-by-date/
    Body: { "date": "YYYY-MM-DD", "language": "es" | "en" | null }
    """
    try:
        experience = Experience.objects.get(id=experience_id)
    except Experience.DoesNotExist:
        return Response(
            {"detail": "Experiencia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    date_str = request.data.get('date')
    if not date_str:
        return Response(
            {"detail": "El campo 'date' (YYYY-MM-DD) es requerido."},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return Response(
            {"detail": "Formato de fecha inválido. Use YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST
        )
    language = request.data.get('language')  # None = both

    qs = TourInstance.objects.filter(
        experience=experience,
        start_datetime__date=target_date,
        status='active',
    )
    if language in ('es', 'en'):
        qs = qs.filter(language=language)
    updated = qs.update(status='blocked')
    return Response({"blocked_count": updated, "date": date_str, "language": language})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def superadmin_experience_instances_unblock_by_date(request, experience_id):
    """
    POST /api/v1/superadmin/experiences/<experience_id>/instances/unblock-by-date/
    Body: { "date": "YYYY-MM-DD", "language": "es" | "en" | null }
    """
    try:
        experience = Experience.objects.get(id=experience_id)
    except Experience.DoesNotExist:
        return Response(
            {"detail": "Experiencia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    date_str = request.data.get('date')
    if not date_str:
        return Response(
            {"detail": "El campo 'date' (YYYY-MM-DD) es requerido."},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return Response(
            {"detail": "Formato de fecha inválido. Use YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST
        )
    language = request.data.get('language')

    qs = TourInstance.objects.filter(
        experience=experience,
        start_datetime__date=target_date,
        status='blocked',
    )
    if language in ('es', 'en'):
        qs = qs.filter(language=language)
    updated = qs.update(status='active')
    return Response({"unblocked_count": updated, "date": date_str, "language": language})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def superadmin_experience_regenerate_instances(request, experience_id):
    """
    POST /api/v1/superadmin/experiences/<experience_id>/regenerate-instances/
    Regenerates tour instances from recurrence_pattern (only creates new, no delete).
    """
    try:
        experience = Experience.objects.get(id=experience_id)
    except Experience.DoesNotExist:
        return Response(
            {"detail": "Experiencia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )
    count = generate_tour_instances_from_pattern(experience)
    return Response({"instances_created": count}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def superadmin_experience_instance_bookings(request, experience_id, instance_id):
    """
    GET /api/v1/superadmin/experiences/<experience_id>/instances/<instance_id>/bookings/
    List bookings (inscritos) for a tour instance.
    """
    try:
        instance = TourInstance.objects.get(id=instance_id, experience_id=experience_id)
    except TourInstance.DoesNotExist:
        return Response(
            {"detail": "Instancia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )
    qs = TourBooking.objects.filter(tour_instance=instance).order_by('-created_at')
    serializer = TourBookingSerializer(qs, many=True)
    return Response({"results": serializer.data})


@api_view(['POST'])
@permission_classes([IsSuperUser])
def superadmin_experience_instance_cancel_and_notify(request, experience_id, instance_id):
    """
    POST /api/v1/superadmin/experiences/<experience_id>/instances/<instance_id>/cancel-and-notify/
    Cancel the tour instance and send cancellation email to all confirmed attendees.
    """
    try:
        instance = TourInstance.objects.get(id=instance_id, experience_id=experience_id)
    except TourInstance.DoesNotExist:
        return Response(
            {"detail": "Instancia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )
    if instance.status == 'cancelled':
        return Response(
            {"detail": "La instancia ya está cancelada.", "status": "cancelled"},
            status=status.HTTP_400_BAD_REQUEST
        )
    instance.status = 'cancelled'
    instance.save(update_fields=['status', 'updated_at'])
    from apps.experiences.tasks import send_tour_instance_cancellation_emails
    result = send_tour_instance_cancellation_emails(instance)
    return Response({
        "status": "cancelled",
        "emails_sent": result['sent_count'],
        "errors": result['errors'],
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def superadmin_experience_bookings_by_date(request, experience_id):
    """
    GET /api/v1/superadmin/experiences/<experience_id>/bookings-by-date/?date=YYYY-MM-DD
    List all bookings for instances on the given date (grouped by instance or flat).
    """
    try:
        experience = Experience.objects.get(id=experience_id)
    except Experience.DoesNotExist:
        return Response(
            {"detail": "Experiencia no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )
    date_str = request.query_params.get('date')
    if not date_str:
        return Response(
            {"detail": "Query param 'date' (YYYY-MM-DD) es requerido."},
            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return Response(
            {"detail": "Formato de fecha inválido. Use YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST
        )

    instances = TourInstance.objects.filter(
        experience=experience,
        start_datetime__date=target_date,
    ).order_by('start_datetime')
    by_instance = []
    for inst in instances:
        bookings = TourBooking.objects.filter(tour_instance=inst, status='confirmed').order_by('created_at')
        ser = TourBookingSerializer(bookings, many=True)
        by_instance.append({
            "instance_id": str(inst.id),
            "start_datetime": timezone.localtime(inst.start_datetime).isoformat(),
            "language": inst.language,
            "bookings": ser.data,
        })
    return Response({"date": date_str, "by_instance": by_instance})
