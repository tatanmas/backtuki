"""
Public endpoint to fetch experience reservation by organizer token.
Used when organizer opens link from WhatsApp payment notification (no auth required).
Fallback: if user is authenticated and is the organizer, allow access without token.
"""
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.experiences.models import ExperienceReservation
from apps.experiences.serializers import ExperienceReservationSerializer
from apps.organizers.models import OrganizerUser
from apps.whatsapp.services.payment_success_notifier import validate_organizer_reservation_token

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_reservation_by_organizer_token(request, id):
    """
    GET /api/v1/reservations/public/<id>/?token=<organizer_token>

    Returns reservation details if:
    1. Token is valid (generated when payment succeeds, 7-day TTL in cache), OR
    2. User is authenticated and is the organizer of the experience.
    """
    token = request.query_params.get('token')
    allow_access = False

    if token:
        reservation_id = validate_organizer_reservation_token(token)
        if reservation_id and str(reservation_id) == str(id):
            allow_access = True

    if not allow_access and request.user.is_authenticated:
        try:
            res = ExperienceReservation.objects.select_related(
                'experience', 'experience__organizer'
            ).get(id=id)
            organizer_user = OrganizerUser.objects.filter(user=request.user).first()
            if organizer_user and res.experience.organizer_id == organizer_user.organizer_id:
                allow_access = True
        except ExperienceReservation.DoesNotExist:
            pass

    if not allow_access:
        if not token:
            return Response(
                {'error': 'Token requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            {'error': 'Enlace inválido o expirado'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        reservation = ExperienceReservation.objects.select_related(
            'experience', 'instance', 'user'
        ).get(id=id)
    except ExperienceReservation.DoesNotExist:
        return Response(
            {'error': 'Reserva no encontrada'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = ExperienceReservationSerializer(reservation)
    return Response(serializer.data)
