"""
SuperAdmin Event Configuration Views
Endpoints para configuración de eventos.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from decimal import Decimal
import logging

from apps.events.models import Event, TicketTier
from api.v1.events.serializers import EventDetailSerializer

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def get_event_detail(request, event_id):
    """
    Get full event detail for superadmin (same shape as organizer GET /events/:id/).
    Allows superadmin to view any event regardless of organizer.
    """
    try:
        event = Event.objects.filter(deleted_at__isnull=True).get(id=event_id)
    except Event.DoesNotExist:
        return Response(
            {'detail': 'Event not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    serializer = EventDetailSerializer(event, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def update_event_service_fee(request, event_id):
    """
    🚀 ENTERPRISE: Update event service fee rate.
    
    PATCH /api/v1/superadmin/events/{id}/service-fee/
    
    Body:
        {
            "service_fee_rate": number | null  (0.0 to 1.0, e.g., 0.15 for 15%)
        }
    """
    try:
        event = Event.objects.get(id=event_id)
        
        fee_rate = request.data.get('service_fee_rate')
        
        # Si es null, eliminar el fee (usar organizer o platform default)
        if fee_rate is None:
            event.service_fee_rate = None
            event.save()
            
            # Calcular el fee efectivo después de eliminar
            effective_fee = float(event.organizer.default_service_fee_rate) if event.organizer.default_service_fee_rate is not None else 0.15
            fee_source = 'organizer' if event.organizer.default_service_fee_rate is not None else 'platform'
            
            logger.info(f"✅ [SuperAdmin] Removed service fee for event {event_id}, will use {fee_source} default")
            
            return Response({
                'success': True,
                'message': f'Service fee eliminado, se usará el default del organizador/plataforma ({effective_fee*100:.1f}%)',
                'event': {
                    'id': str(event.id),
                    'title': event.title,
                    'service_fee_rate': None,
                    'effective_service_fee_rate': effective_fee,
                    'service_fee_source': fee_source
                }
            }, status=status.HTTP_200_OK)
        
        # Validar que esté entre 0 y 1
        try:
            fee_rate_decimal = Decimal(str(fee_rate))
            if fee_rate_decimal < 0 or fee_rate_decimal > 1:
                return Response({
                    'success': False,
                    'message': 'El service fee debe estar entre 0 y 1 (0% a 100%)'
                }, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'message': 'Service fee inválido'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        event.service_fee_rate = fee_rate_decimal
        event.save()
        
        logger.info(f"✅ [SuperAdmin] Updated service fee for event {event_id}: {fee_rate_decimal}")
        
        return Response({
            'success': True,
            'message': 'Service fee actualizado exitosamente',
            'event': {
                'id': str(event.id),
                'title': event.title,
                'service_fee_rate': float(fee_rate_decimal),
                'effective_service_fee_rate': float(fee_rate_decimal),
                'service_fee_source': 'event'
            }
        }, status=status.HTTP_200_OK)
        
    except Event.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Event not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error updating event service fee: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error updating event service fee: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def update_ticket_tier_service_fee(request, event_id, tier_id):
    """
    Update service_fee_rate for a specific ticket tier (superadmin only).
    Body: { "service_fee_rate": number | null } (0–1 e.g. 0.15 = 15%; null = use inheritance).
    """
    try:
        event = Event.objects.filter(deleted_at__isnull=True).get(id=event_id)
    except Event.DoesNotExist:
        return Response(
            {'success': False, 'message': 'Event not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    try:
        tier = TicketTier.objects.get(id=tier_id, event=event)
    except TicketTier.DoesNotExist:
        return Response(
            {'success': False, 'message': 'Ticket tier not found for this event'},
            status=status.HTTP_404_NOT_FOUND
        )

    fee_rate = request.data.get('service_fee_rate')

    if fee_rate is None:
        tier.service_fee_rate = None
        tier.save()
        effective = tier.get_service_fee_rate()
        logger.info(f"✅ [SuperAdmin] Removed tier service fee for tier {tier_id}, effective {effective}")
        return Response({
            'success': True,
            'message': 'Tier service fee removed; will use event/organizer/platform default',
            'ticket_tier': {
                'id': str(tier.id),
                'name': tier.name,
                'service_fee_rate': None,
                'effective_service_fee_rate': float(effective),
            }
        }, status=status.HTTP_200_OK)

    try:
        fee_rate_decimal = Decimal(str(fee_rate))
        if fee_rate_decimal < 0 or fee_rate_decimal > 1:
            return Response({
                'success': False,
                'message': 'service_fee_rate must be between 0 and 1 (0% to 100%)',
            }, status=status.HTTP_400_BAD_REQUEST)
    except (ValueError, TypeError):
        return Response({
            'success': False,
            'message': 'Invalid service_fee_rate',
        }, status=status.HTTP_400_BAD_REQUEST)

    tier.service_fee_rate = fee_rate_decimal
    tier.save()
    logger.info(f"✅ [SuperAdmin] Updated tier service fee for tier {tier_id}: {fee_rate_decimal}")
    return Response({
        'success': True,
        'message': 'Tier service fee updated',
        'ticket_tier': {
            'id': str(tier.id),
            'name': tier.name,
            'service_fee_rate': float(fee_rate_decimal),
            'effective_service_fee_rate': float(fee_rate_decimal),
        }
    }, status=status.HTTP_200_OK)
