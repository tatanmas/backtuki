"""
Message processing service for WhatsApp messages.

This service handles:
- Message saving with idempotency
- Chat creation/updates
- Reservation code detection
- Experience-operator-group routing
"""
import logging
from typing import Dict, Optional, Tuple
from django.utils import timezone
from django.db import transaction

from apps.whatsapp.models import (
    WhatsAppMessage, WhatsAppChat, WhatsAppReservationCode,
    WhatsAppReservationRequest, TourOperator
)
from apps.whatsapp.services.message_parser import MessageParser
from apps.whatsapp.services.reservation_handler import ReservationHandler
from apps.whatsapp.services.operator_notifier import OperatorNotifier
from apps.whatsapp.services.experience_operator_service import ExperienceOperatorService
from apps.experiences.models import Experience

logger = logging.getLogger(__name__)


class MessageProcessor:
    """Service for processing incoming WhatsApp messages."""
    
    @staticmethod
    def parse_timestamp(raw_timestamp) -> timezone.datetime:
        """
        Parse timestamp from Node.js service (can be seconds or milliseconds).
        
        Args:
            raw_timestamp: Timestamp as int/float (seconds or milliseconds)
            
        Returns:
            timezone-aware datetime
        """
        if isinstance(raw_timestamp, (int, float)) and raw_timestamp > 0:
            try:
                # whatsapp-web.js returns timestamps in seconds
                if raw_timestamp > 10000000000:  # Milliseconds
                    return timezone.datetime.fromtimestamp(
                        raw_timestamp / 1000, tz=timezone.utc
                    )
                else:  # Seconds
                    return timezone.datetime.fromtimestamp(
                        raw_timestamp, tz=timezone.utc
                    )
            except (ValueError, OSError) as e:
                logger.warning(f"Error parsing timestamp {raw_timestamp}: {e}")
        
        return timezone.now()
    
    @staticmethod
    @transaction.atomic
    def get_or_create_chat(
        chat_id: str,
        chat_type: str,
        chat_name: Optional[str] = None,
        whatsapp_name: Optional[str] = None,
        profile_picture_url: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Tuple[WhatsAppChat, bool]:
        """
        Get or create a WhatsApp chat.
        
        Args:
            chat_id: WhatsApp chat ID (e.g., '56912345678@c.us' or '120363123456789012@g.us')
            chat_type: 'individual' or 'group'
            chat_name: Display name for the chat
            whatsapp_name: WhatsApp name from contact
            profile_picture_url: Profile picture URL
            phone: Phone number (for individual chats)
            
        Returns:
            Tuple of (WhatsAppChat, created: bool)
        """
        if not chat_id:
            raise ValueError("chat_id is required")
        
        # Determine best name to use
        display_name = chat_name
        if not display_name or display_name == 'Unknown':
            if chat_type == 'individual' and phone:
                # Format phone number
                phone_clean = phone.replace('@c.us', '').replace('@g.us', '').replace('@lid', '')
                if phone_clean and phone_clean.isdigit():
                    # Format Chilean number
                    if phone_clean.startswith('56') and len(phone_clean) == 11:
                        display_name = f"+{phone_clean[:2]} {phone_clean[2:3]} {phone_clean[3:7]} {phone_clean[7:]}"
                    else:
                        display_name = f"+{phone_clean}"
                else:
                    display_name = phone_clean or chat_id.replace('@c.us', '').replace('@g.us', '')
            else:
                display_name = chat_id.replace('@c.us', '').replace('@g.us', '')
        
        defaults = {
            'name': display_name,
            'type': chat_type,
            'is_active': True,
            'whatsapp_name': whatsapp_name or '',
            'profile_picture_url': profile_picture_url or ''
        }
        
        chat, created = WhatsAppChat.objects.get_or_create(
            chat_id=chat_id,
            defaults=defaults
        )
        
        if not created:
            # Update if we have better information
            update_fields = []
            
            if display_name and display_name != chat.name and display_name != 'Unknown':
                if (chat.name == 'Unknown' or 
                    'Unknown' in chat.name or
                    len(display_name) > len(chat.name) or
                    (display_name.startswith('+') and not chat.name.startswith('+'))):
                    chat.name = display_name
                    update_fields.append('name')
            
            if whatsapp_name and whatsapp_name != chat.whatsapp_name:
                chat.whatsapp_name = whatsapp_name
                update_fields.append('whatsapp_name')
            
            if profile_picture_url and profile_picture_url != chat.profile_picture_url:
                chat.profile_picture_url = profile_picture_url
                update_fields.append('profile_picture_url')
            
            if chat.type != chat_type:
                chat.type = chat_type
                update_fields.append('type')
            
            if update_fields:
                chat.save(update_fields=update_fields)
        
        return chat, created
    
    @staticmethod
    @transaction.atomic
    def save_message(
        whatsapp_id: str,
        phone: str,
        text: str,
        chat_id: str,
        chat_type: str,
        timestamp: timezone.datetime,
        from_me: bool = False,
        chat_name: Optional[str] = None,
        whatsapp_name: Optional[str] = None,
        profile_picture_url: Optional[str] = None,
        sender_name: Optional[str] = None,
        sender_phone: Optional[str] = None
    ) -> Tuple[Optional[WhatsAppMessage], bool]:
        """
        Save a WhatsApp message with idempotency.
        
        Args:
            whatsapp_id: Unique WhatsApp message ID
            phone: Phone number or group ID
            text: Message text
            chat_id: WhatsApp chat ID
            chat_type: 'individual' or 'group'
            timestamp: Message timestamp
            from_me: Whether message was sent by us
            chat_name: Chat display name
            whatsapp_name: WhatsApp contact name
            profile_picture_url: Profile picture URL
            sender_name: Sender name (for group messages)
            sender_phone: Sender phone (for group messages)
            
        Returns:
            Tuple of (WhatsAppMessage or None, is_new: bool)
        """
        # Check for idempotency
        existing_message = WhatsAppMessage.objects.filter(whatsapp_id=whatsapp_id).first()
        if existing_message:
            logger.debug(f"Message {whatsapp_id} already exists")
            return existing_message, False
        
        # Get or create chat
        chat, _ = MessageProcessor.get_or_create_chat(
            chat_id=chat_id,
            chat_type=chat_type,
            chat_name=chat_name,
            whatsapp_name=whatsapp_name,
            profile_picture_url=profile_picture_url,
            phone=phone
        )
        
        # Prepare metadata for group messages
        message_metadata = {}
        if chat_type == 'group':
            if sender_name:
                message_metadata['sender_name'] = sender_name
            if sender_phone:
                message_metadata['sender_phone'] = sender_phone
        
        # Determine message type
        message_type = 'out' if from_me else 'in'
        
        # Create message
        message = WhatsAppMessage.objects.create(
            whatsapp_id=whatsapp_id,
            phone=phone,
            type=message_type,
            content=text,
            timestamp=timestamp,
            chat=chat,
            is_automated=False if from_me else False,  # Messages from phone are not automated
            metadata=message_metadata if message_metadata else {}
        )
        
        logger.info(f"💾 Saved message {message.id} (type: {message_type}, from_me: {from_me})")
        
        return message, True
    
    @staticmethod
    @transaction.atomic
    def process_reservation_code(
        message: WhatsAppMessage,
        reservation_code: str
    ) -> Optional[WhatsAppReservationRequest]:
        """
        Process a reservation code from a message.
        
        Args:
            message: WhatsAppMessage instance
            reservation_code: Reservation code (e.g., 'RES-ABC123')
            
        Returns:
            WhatsAppReservationRequest if created, None otherwise
        """
        # Find reservation code
        try:
            code_obj = WhatsAppReservationCode.objects.get(code=reservation_code)
        except WhatsAppReservationCode.DoesNotExist:
            logger.warning(f"Reservation code {reservation_code} not found")
            return None
        
        # Validate code is not expired
        from apps.whatsapp.services.reservation_code_generator import ReservationCodeGenerator
        if not ReservationCodeGenerator.validate_code(reservation_code):
            logger.warning(f"Reservation code {reservation_code} is invalid or expired")
            return None
        
        # Check if already processed
        if code_obj.linked_reservation:
            logger.info(f"Reservation code {reservation_code} already linked to reservation {code_obj.linked_reservation.id}")
            return code_obj.linked_reservation
        
        # Get experience from checkout data
        experience = None
        if code_obj.checkout_data:
            experience_id = code_obj.checkout_data.get('experience_id')
            if experience_id:
                try:
                    experience = Experience.objects.get(id=experience_id)
                except Experience.DoesNotExist:
                    logger.warning(f"Experience {experience_id} not found for code {reservation_code}")
        
        if not experience:
            logger.warning(f"No experience found for reservation code {reservation_code}")
            return None
        
        # Get operator and group for this experience
        group_info = ExperienceOperatorService.get_experience_whatsapp_group(experience)
        if not group_info:
            logger.warning(f"No WhatsApp group configured for experience {experience.title}")
            # Still create reservation, but operator will need to be assigned manually
            operator = None
        else:
            # Find operator from group assignment
            chat = message.chat
            if chat.assigned_operator:
                operator = chat.assigned_operator
            else:
                # Try to find operator from experience bindings
                operator_binding = experience.operator_bindings.filter(is_active=True).first()
                operator = operator_binding.tour_operator if operator_binding else None
        
        if not operator:
            logger.warning(f"No operator found for experience {experience.title}")
            # Create reservation without operator - will need manual assignment
            reservation = WhatsAppReservationRequest.objects.create(
                whatsapp_message=message,
                tour_code=reservation_code,
                passengers=code_obj.checkout_data.get('participants', {}).get('total', 1) if code_obj.checkout_data else 1,
                operator=None,  # Will be assigned later
                experience=experience,
                status='received',
                timeout_at=None  # No timeout until operator is assigned
            )
            
            # Link code to reservation
            code_obj.linked_reservation = reservation
            code_obj.save()
            
            logger.info(f"Created reservation {reservation.id} without operator (needs manual assignment)")
            return reservation
        
        # Parse message for additional info
        parsed = MessageParser.parse_message(message.content)
        passengers = parsed.get('passengers') or (
            code_obj.checkout_data.get('participants', {}).get('total', 1) if code_obj.checkout_data else 1
        )
        
        # Create reservation
        reservation = ReservationHandler.create_reservation(
            message=message,
            tour_code=reservation_code,
            passengers=passengers,
            operator=operator,
            experience=experience
        )
        
        # Link code to reservation
        code_obj.linked_reservation = reservation
        code_obj.save()
        
        # Notify operator (handled by ReservationHandler.mark_operator_notified)
        ReservationHandler.mark_operator_notified(reservation)
        logger.info(f"✅ Notified operator for reservation {reservation.id}")
        
        return reservation
    
    @staticmethod
    def process_incoming_message(data: Dict) -> Dict:
        """
        Process an incoming WhatsApp message.
        
        Args:
            data: Message data from Node.js service
            
        Returns:
            Dict with processing result
        """
        whatsapp_id = data.get('id')
        if not whatsapp_id:
            return {'status': 'error', 'message': 'Missing message ID'}
        
        # Check idempotency
        existing_message = WhatsAppMessage.objects.filter(whatsapp_id=whatsapp_id).first()
        if existing_message and existing_message.processed:
            return {
                'status': 'already_processed',
                'message_id': str(existing_message.id)
            }
        
        from_me = data.get('from_me', False)
        
        # Parse timestamp
        raw_timestamp = data.get('timestamp')
        message_timestamp = MessageProcessor.parse_timestamp(raw_timestamp)
        
        # Save message
        message, is_new = MessageProcessor.save_message(
            whatsapp_id=whatsapp_id,
            phone=data.get('phone', ''),
            text=data.get('text', ''),
            chat_id=data.get('chat_id'),
            chat_type=data.get('chat_type', 'individual'),
            timestamp=message_timestamp,
            from_me=from_me,
            chat_name=data.get('chat_name'),
            whatsapp_name=data.get('whatsapp_name'),
            profile_picture_url=data.get('profile_picture_url'),
            sender_name=data.get('sender_name'),
            sender_phone=data.get('sender_phone')
        )
        
        if not message:
            return {'status': 'error', 'message': 'Failed to save message'}
        
        # If message is from us (phone), just save it and return
        if from_me:
            return {
                'status': 'saved',
                'message_id': str(message.id),
                'type': 'outgoing'
            }
        
        # Mark as processed
        message.processed = True
        message.save(update_fields=['processed'])
        
        # Check for reservation code
        parsed = MessageParser.parse_message(message.content)
        reservation_code = parsed.get('reservation_code')
        
        if reservation_code:
            try:
                reservation = MessageProcessor.process_reservation_code(message, reservation_code)
                if reservation:
                    return {
                        'status': 'reservation_created',
                        'message_id': str(message.id),
                        'reservation_id': str(reservation.id)
                    }
            except Exception as e:
                logger.exception(f"Error processing reservation code {reservation_code}: {e}")
                # Continue - message is saved even if reservation processing fails
        
        return {
            'status': 'processed',
            'message_id': str(message.id)
        }
    
    @staticmethod
    def _process_operator_response(data: Dict) -> Dict:
        """
        Process operator response (1=confirm, 2=reject).
        
        Args:
            data: Message data with text and phone
            
        Returns:
            Dict with processing result
        """
        text = data.get('text', '').strip().lower()
        is_confirm = text in ['1', 'sí', 'si', 'yes', 'confirmar']
        phone = data.get('phone', '')
        
        # Find operator by phone
        operator = TourOperator.objects.filter(
            whatsapp_number=phone
        ).first() or TourOperator.objects.filter(
            contact_phone=phone
        ).first()
        
        if not operator:
            logger.warning(f"Operator not found for phone {phone}")
            return {'status': 'operator_not_found'}
        
        # Find most recent pending reservation for this operator
        reservation = WhatsAppReservationRequest.objects.filter(
            operator=operator,
            status='operator_notified'
        ).order_by('-created_at').first()
        
        if not reservation:
            logger.info(f"No pending reservation found for operator {phone}")
            return {'status': 'no_pending_reservation'}
        
        # Update reservation status (notifications are handled by ReservationHandler)
        if is_confirm:
            ReservationHandler.confirm_reservation(reservation)
            logger.info(f"Reservation {reservation.id} confirmed by operator {operator.name}")
        else:
            ReservationHandler.reject_reservation(reservation)
            logger.info(f"Reservation {reservation.id} rejected by operator {operator.name}")
        
        return {
            'status': 'processed',
            'confirmed': is_confirm,
            'reservation_id': str(reservation.id)
        }

