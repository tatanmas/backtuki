"""
SuperAdmin Organizer Configuration Views
Endpoints para configuración de organizadores.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from decimal import Decimal
import logging

from apps.organizers.models import Organizer

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def update_organizer_template(request, organizer_id):
    """
    🚀 ENTERPRISE: Update experience dashboard template for an organizer.
    
    PATCH /api/v1/superadmin/organizers/{id}/template/
    
    Body:
        {
            "experience_dashboard_template": "principal" | "v0"
        }
    """
    try:
        organizer = Organizer.objects.get(id=organizer_id)
        template = request.data.get('experience_dashboard_template')
        
        if template not in ['v0', 'principal']:
            return Response({
                'success': False,
                'message': 'Template must be "v0" or "principal"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Only allow if organizer has experience module
        if not organizer.has_experience_module:
            return Response({
                'success': False,
                'message': 'Organizer does not have experience module enabled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        organizer.experience_dashboard_template = template
        organizer.save()
        
        logger.info(f"✅ [SuperAdmin] Updated template for organizer {organizer_id}: {template}")
        
        return Response({
            'success': True,
            'message': 'Template updated successfully',
            'organizer': {
                'id': str(organizer.id),
                'name': organizer.name,
                'experience_dashboard_template': organizer.experience_dashboard_template
            }
        }, status=status.HTTP_200_OK)
        
    except Organizer.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Organizer not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error updating template: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error updating template: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def update_organizer_modules(request, organizer_id):
    """
    🚀 ENTERPRISE: Update organizer modules (events, experiences, accommodations) and student center flag.
    
    PATCH /api/v1/superadmin/organizers/{id}/modules/
    
    Body:
        {
            "has_events_module": bool,
            "has_experience_module": bool,
            "has_accommodation_module": bool,
            "is_student_center": bool (optional)
        }
    """
    try:
        organizer = Organizer.objects.get(id=organizer_id)
        
        has_events = request.data.get('has_events_module')
        has_experience = request.data.get('has_experience_module')
        has_accommodation = request.data.get('has_accommodation_module')
        is_student_center = request.data.get('is_student_center')
        
        # Validar que al menos un módulo esté activo
        if not (has_events or has_experience or has_accommodation):
            return Response({
                'success': False,
                'message': 'Al menos un módulo debe estar activo'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Actualizar módulos
        if has_events is not None:
            organizer.has_events_module = has_events
        if has_experience is not None:
            organizer.has_experience_module = has_experience
        if has_accommodation is not None:
            organizer.has_accommodation_module = has_accommodation
        if is_student_center is not None:
            organizer.is_student_center = is_student_center
        
        organizer.save()
        
        logger.info(f"✅ [SuperAdmin] Updated modules for organizer {organizer_id}: events={has_events}, experience={has_experience}, accommodation={has_accommodation}, is_student_center={is_student_center}")
        
        return Response({
            'success': True,
            'message': 'Módulos actualizados exitosamente',
            'organizer': {
                'id': str(organizer.id),
                'name': organizer.name,
                'has_events_module': organizer.has_events_module,
                'has_experience_module': organizer.has_experience_module,
                'has_accommodation_module': organizer.has_accommodation_module,
                'is_student_center': organizer.is_student_center,
            }
        }, status=status.HTTP_200_OK)
        
    except Organizer.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Organizer not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error updating modules: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error updating modules: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])
def update_organizer_service_fee(request, organizer_id):
    """
    🚀 ENTERPRISE: Update organizer service fee rate.
    
    PATCH /api/v1/superadmin/organizers/{id}/service-fee/
    
    Body:
        {
            "default_service_fee_rate": number | null  (0.0 to 1.0, e.g., 0.15 for 15%)
        }
    """
    try:
        organizer = Organizer.objects.get(id=organizer_id)
        
        fee_rate = request.data.get('default_service_fee_rate')
        
        # Si es null, eliminar el fee (usar platform default)
        if fee_rate is None:
            organizer.default_service_fee_rate = None
            organizer.save()
            
            logger.info(f"✅ [SuperAdmin] Removed service fee for organizer {organizer_id}, will use platform default")
            
            return Response({
                'success': True,
                'message': 'Service fee eliminado, se usará el default de la plataforma (15%)',
                'organizer': {
                    'id': str(organizer.id),
                    'name': organizer.name,
                    'default_service_fee_rate': None,
                    'effective_service_fee_rate': 0.15,
                    'service_fee_source': 'platform'
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
        
        organizer.default_service_fee_rate = fee_rate_decimal
        organizer.save()
        
        logger.info(f"✅ [SuperAdmin] Updated service fee for organizer {organizer_id}: {fee_rate_decimal}")
        
        return Response({
            'success': True,
            'message': 'Service fee actualizado exitosamente',
            'organizer': {
                'id': str(organizer.id),
                'name': organizer.name,
                'default_service_fee_rate': float(fee_rate_decimal),
                'effective_service_fee_rate': float(fee_rate_decimal),
                'service_fee_source': 'organizer'
            }
        }, status=status.HTTP_200_OK)
        
    except Organizer.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Organizer not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error updating service fee: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error updating service fee: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
