# backtuki/api/v1/whatsapp/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import re
import requests
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
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
from decimal import Decimal

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
        text = data.get('text', '') or ''
        logger.info(
            f"Received message: id={data.get('id')} from={data.get('phone')} from_me={data.get('from_me', False)} "
            f"text_len={len(text)} text_preview={repr(text[:150]) if text else '(empty)'}"
        )
        
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


def _serialize_decimal(value):
    """Convert Decimal or nested structures to JSON-safe primitives."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _serialize_decimal(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize_decimal(item) for item in value]
    return value


@api_view(['GET'])
@permission_classes([AllowAny])
def reservation_by_code(request):
    """
    Retrieve reservation details linked to a WhatsApp code.

    Used by the checkout frontend to pre-fill information when a customer
    follows the payment link shared via WhatsApp.
    """
    code = request.query_params.get('codigo') or request.query_params.get('code')
    if not code:
        return Response(
            {'error': 'El parámetro codigo es obligatorio.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        code_obj = WhatsAppReservationCode.objects.select_related(
            'experience', 'linked_reservation', 'linked_reservation__linked_experience_reservation',
            'linked_reservation__whatsapp_message'
        ).get(code=code)
    except WhatsAppReservationCode.DoesNotExist:
        return Response(
            {'error': 'El código indicado no existe o no pertenece a esta instancia.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if code_obj.status == 'expired' or code_obj.is_expired():
        return Response(
            {'error': 'El código de reserva ha expirado.'},
            status=status.HTTP_410_GONE
        )

    reservation = code_obj.linked_reservation
    if not reservation:
        return Response(
            {'error': 'La solicitud aún no ha sido vinculada a una reserva.'},
            status=status.HTTP_409_CONFLICT
        )

    if reservation.status not in ['availability_confirmed', 'confirmed']:
        return Response(
            {
                'error': 'La reserva todavía no está lista para el pago.',
                'status': reservation.status
            },
            status=status.HTTP_409_CONFLICT
        )

    checkout_data = code_obj.checkout_data or {}
    participants = checkout_data.get('participants') or {}
    pricing = _serialize_decimal(checkout_data.get('pricing') or {})
    total = pricing.get('total') or checkout_data.get('total_price')
    if isinstance(total, Decimal):
        total = float(total)

    experience = code_obj.experience
    experience_data = None
    if experience:
        experience_data = {
            'id': str(experience.id),
            'title': experience.title,
            'slug': experience.slug,
            'price': float(experience.price) if isinstance(experience.price, Decimal) else experience.price,
            'currency': getattr(experience, 'currency', 'CLP'),
        }

    exp_res = getattr(reservation, 'linked_experience_reservation', None)
    experience_reservation_id = str(exp_res.reservation_id) if exp_res else None

    # Customer: merge checkout_data.customer with WhatsApp phone from sender
    from core.phone_utils import normalize_phone_e164, format_phone_display
    from django.contrib.auth import get_user_model
    User = get_user_model()

    customer = dict(checkout_data.get('customer') or {})
    raw_phone = customer.get('phone') or ''
    if not raw_phone and reservation.whatsapp_message:
        msg = reservation.whatsapp_message
        raw = getattr(msg, 'phone', '') or ''
        meta = getattr(msg, 'metadata', None) or {}
        raw = raw or meta.get('sender_phone') or meta.get('author_phone') or meta.get('phone') or ''
        raw_phone = (raw or '').replace('@c.us', '').replace('@g.us', '').replace('@lid', '').replace(' ', '').strip()

    normalized_phone = normalize_phone_e164(raw_phone) if raw_phone else ''
    if normalized_phone:
        customer['phone'] = format_phone_display(normalized_phone)
        # Lookup user by phone for returning customers - pre-fill email, name
        try:
            user_by_phone = User.objects.filter(
                Q(phone_number=normalized_phone) | Q(phone_number=raw_phone)
            ).first()
            if user_by_phone:
                if not customer.get('email'):
                    customer['email'] = user_by_phone.email or ''
                if not customer.get('name') and (user_by_phone.first_name or user_by_phone.last_name):
                    customer['name'] = f"{user_by_phone.first_name or ''} {user_by_phone.last_name or ''}".strip()
                if not customer.get('first_name') and user_by_phone.first_name:
                    customer['first_name'] = user_by_phone.first_name
                if not customer.get('last_name') and user_by_phone.last_name:
                    customer['last_name'] = user_by_phone.last_name
        except Exception:
            pass

    response_data = {
        'code': code_obj.code,
        'status': reservation.status,
        'expires_at': code_obj.expires_at.isoformat() if code_obj.expires_at else None,
        'experience': experience_data,
        'experience_reservation_id': experience_reservation_id,
        'participants': {
            'adults': participants.get('adults', 0),
            'children': participants.get('children', 0),
            'infants': participants.get('infants', 0),
        },
        'date': checkout_data.get('date'),
        'time': checkout_data.get('time'),
        'pricing': pricing,
        'total': total,
        'currency': pricing.get('currency') or getattr(experience, 'currency', 'CLP') if experience else None,
        'customer': customer,
        'payment_link': reservation.payment_link,
        'payment_link_sent_at': reservation.payment_link_sent_at.isoformat() if reservation.payment_link_sent_at else None,
        'allow_payment': reservation.payment_received_at is None,
    }

    return Response(response_data, status=status.HTTP_200_OK)


