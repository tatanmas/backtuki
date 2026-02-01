"""
SuperAdmin Event Configuration Views
Endpoints para configuración de eventos.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from decimal import Decimal
import logging

from apps.events.models import Event

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


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
