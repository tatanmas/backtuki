# backtuki/api/v1/whatsapp/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import re
import requests
from django.utils import timezone
from django.db import transaction
import logging

from apps.whatsapp.models import (
    WhatsAppMessage, WhatsAppReservationRequest, TourOperator, 
    WhatsAppSession, WhatsAppChat, WhatsAppReservationCode
)
from apps.whatsapp.services.reservation_handler import ReservationHandler
from apps.whatsapp.services.operator_notifier import OperatorNotifier
from apps.whatsapp.services.message_parser import MessageParser
from apps.whatsapp.services.message_processor import MessageProcessor
from apps.whatsapp.services.reservation_code_generator import ReservationCodeGenerator
from apps.whatsapp.services.group_notification_service import GroupNotificationService
from apps.experiences.models import Experience

logger = logging.getLogger(__name__)


def send_message(phone, text, is_automated=True, group_id=None):
    """
    Send a message via WhatsApp service and save it as automated.
    
    Args:
        phone: Phone number (for individual chats) or empty string (for groups)
        text: Message text
        is_automated: Whether this is an automated message
        group_id: Optional group ID for group messages
    """
    from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
    from apps.whatsapp.models import WhatsAppMessage, WhatsAppChat
    from django.utils import timezone
    
    try:
        service = WhatsAppWebService()
        service.send_message(phone, text, group_id=group_id)
        
        # Guardar mensaje saliente como automatizado
        try:
            # Buscar chat por phone o group_id
            if group_id:
                chat = WhatsAppChat.objects.filter(chat_id=group_id).first()
            else:
                chat = WhatsAppChat.objects.filter(
                    chat_id__icontains=phone.replace('@c.us', '').replace('@g.us', '')
                ).first()
            
            if chat:
                WhatsAppMessage.objects.create(
                    whatsapp_id=f"auto_{timezone.now().timestamp()}",
                    phone=phone or group_id or '',
                    type='out',
                    content=text,
                    timestamp=timezone.now(),
                    processed=True,
                    chat=chat,
                    is_automated=is_automated
                )
        except Exception as e:
            logger.warning(f"Could not save automated message: {e}")
            
    except Exception as e:
        logger.error(f"Error sending message: {e}")


@api_view(['POST'])
@permission_classes([AllowAny])  # TODO: Add proper authentication
def process_message(request):
    """Process incoming WhatsApp message - now using MessageProcessor service."""
    try:
        data = request.data
        logger.info(f"Received message: {data.get('id')} from {data.get('phone')} (FromMe: {data.get('from_me', False)})")
        
        # Use MessageProcessor service for all processing
        result = MessageProcessor.process_incoming_message(data)
        
        # Map result status to HTTP status
        if result.get('status') == 'error':
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def process_operator_response_internal(data):
    """Internal function to process operator responses - delegates to MessageProcessor."""
    from apps.whatsapp.services.message_processor import MessageProcessor
    result = MessageProcessor._process_operator_response(data)
    return Response(result)


@api_view(['POST'])
def process_operator_response(request):
    """Process operator response (1=confirm, 2=reject)."""
    data = request.data
    text = data.get('text', '').strip().lower()
    
    # Check if message is a confirmation response
    if text not in ['1', '2', 'sí', 'si', 'yes', 'no', 'confirmar', 'rechazar']:
        return Response({'status': 'not_operator_response'})
    
    # Determine response type
    is_confirm = text in ['1', 'sí', 'si', 'yes', 'confirmar']
    
    # Find pending reservation for this operator
    operator = TourOperator.objects.filter(
        whatsapp_number=data['phone']
    ).first() or TourOperator.objects.filter(
        contact_phone=data['phone']
    ).first()
    
    if not operator:
        return Response({'status': 'operator_not_found'})
    
    # Find most recent pending reservation for this operator
    reservation = WhatsAppReservationRequest.objects.filter(
        operator=operator,
        status='operator_notified'
    ).order_by('-created_at').first()
    
    if not reservation:
        return Response({'status': 'no_pending_reservation'})
    
    # Update reservation status (notifications are handled by ReservationHandler)
    if is_confirm:
        ReservationHandler.confirm_reservation(reservation)
    else:
        ReservationHandler.reject_reservation(reservation)
    
    return Response({
        'status': 'processed',
        'reservation_id': str(reservation.id),
        'confirmed': is_confirm
    })


@api_view(['POST'])
@permission_classes([AllowAny])  # TODO: Add proper authentication
def webhook_status(request):
    """Handle status updates from WhatsApp service."""
    data = request.data
    
    try:
        # Get or create session
        session = WhatsAppSession.objects.first()
        if not session:
            session = WhatsAppSession.objects.create(
                status='disconnected',
                created_at=timezone.now()
            )
        
        status_value = data.get('status', 'disconnected')
        session.status = status_value
        session.phone_number = data.get('phone_number', '')
        session.name = data.get('name', '')
        session.save()
        
        return Response({'status': 'ok'}, status=status.HTTP_200_OK)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Error processing WhatsApp status webhook")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])  # TODO: Add proper authentication
def webhook_qr(request):
    """Handle QR code updates from WhatsApp service."""
    data = request.data
    qr = data.get('qr')
    
    try:
        # Get or create session
        session = WhatsAppSession.objects.first()
        if not session:
            session = WhatsAppSession.objects.create(
                status='qr_pending',
                created_at=timezone.now()
            )
        
        session.qr_code = qr
        session.status = 'qr_pending'
        session.save()
        
        return Response({'status': 'ok'}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("Error processing WhatsApp QR webhook")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])  # TODO: Add proper authentication
def generate_reservation_code(request):
    """Generate a unique reservation code for checkout."""
    experience_id = request.data.get('experience_id')
    checkout_data = request.data.get('checkout_data', {})
    
    if not experience_id:
        return Response({
            'error': 'experience_id is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        code_obj = ReservationCodeGenerator.generate_code(experience_id, checkout_data)
        
        return Response({
            'code': code_obj.code,
            'expires_at': code_obj.expires_at.isoformat(),
            'code_id': str(code_obj.id)
        }, status=status.HTTP_201_CREATED)
    
    except ValueError as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(f"Error generating reservation code: {e}")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


