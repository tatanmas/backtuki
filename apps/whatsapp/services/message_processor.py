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
from apps.whatsapp.services.group_notification_service import GroupNotificationService
from apps.whatsapp.services.operator_notifier import OperatorNotifier
from apps.whatsapp.services.experience_operator_service import ExperienceOperatorService
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
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
        sender_phone: Optional[str] = None,
        media_type: Optional[str] = None,
        reply_to_whatsapp_id: Optional[str] = None,
    ) -> Tuple[Optional[WhatsAppMessage], bool]:
        """
        Save a WhatsApp message with idempotency (enterprise: media, reply).
        
        Args:
            whatsapp_id: Unique WhatsApp message ID
            phone: Phone number or group ID
            text: Message text (or placeholder for media)
            chat_id: WhatsApp chat ID
            chat_type: 'individual' or 'group'
            timestamp: Message timestamp
            from_me: Whether message was sent by us
            chat_name: Chat display name
            whatsapp_name: WhatsApp contact name
            profile_picture_url: Profile picture URL
            sender_name: Sender name (for group messages)
            sender_phone: Sender phone (for group messages)
            media_type: chat, ptt, audio, image, video, document, etc.
            reply_to_whatsapp_id: WhatsApp ID of quoted message
            
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
        
        create_kwargs = {
            'whatsapp_id': whatsapp_id,
            'phone': phone,
            'type': message_type,
            'content': text,
            'timestamp': timestamp,
            'chat': chat,
            'is_automated': False,
            'metadata': message_metadata if message_metadata else {},
        }
        if media_type:
            create_kwargs['media_type'] = media_type
        if reply_to_whatsapp_id:
            create_kwargs['reply_to_whatsapp_id'] = reply_to_whatsapp_id
        message = WhatsAppMessage.objects.create(**create_kwargs)

        # Update chat last_message_at and last_message_preview for ordering/preview
        update_fields = []
        if not chat.last_message_at or timestamp > chat.last_message_at:
            chat.last_message_at = timestamp
            update_fields.append('last_message_at')
        preview = (text or '')[:255]
        if preview and preview != (chat.last_message_preview or ''):
            chat.last_message_preview = preview
            update_fields.append('last_message_preview')
        if update_fields:
            chat.save(update_fields=update_fields)

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
            logger.warning(
                f"Reservation code {reservation_code} NOT FOUND in DB. "
                "Code must be generated via frontend before sending WhatsApp message."
            )
            return None

        # Validate code is not expired
        from apps.whatsapp.services.reservation_code_generator import ReservationCodeGenerator
        if not ReservationCodeGenerator.validate_code(reservation_code):
            logger.warning(
                f"Reservation code {reservation_code} is EXPIRED or status != pending. "
                f"Expires: {code_obj.expires_at}, status: {code_obj.status}"
            )
            return None
        
        # Check if already processed
        if code_obj.linked_reservation:
            logger.info(f"Reservation code {reservation_code} already linked to reservation {code_obj.linked_reservation.id}")
            return code_obj.linked_reservation
        
        # Get experience - first try direct relation, then checkout_data
        experience = code_obj.experience
        
        if not experience and code_obj.checkout_data:
            experience_id = code_obj.checkout_data.get('experience_id')
            if experience_id:
                try:
                    experience = Experience.objects.get(id=experience_id)
                except Experience.DoesNotExist:
                    logger.warning(f"Experience {experience_id} not found for code {reservation_code}")
        
        if not experience:
            logger.warning(
                f"No experience found for reservation code {reservation_code}. "
                f"code_obj.experience={code_obj.experience_id}, checkout_data.experience_id={code_obj.checkout_data.get('experience_id') if code_obj.checkout_data else None}"
            )
            return None

        logger.info(f"Experience found: {experience.title} (id={experience.id})")

        # Get operator and group for this experience
        group_info = ExperienceOperatorService.get_experience_whatsapp_group(experience)
        if not group_info:
            logger.warning(
                f"No WhatsApp group configured for experience {experience.title}. "
                "Operator must have default_whatsapp_group or experience must have ExperienceGroupBinding."
            )
            operator = None
        else:
            # Operator: 1) from group_info (binding/group), 2) chat.assigned_operator, 3) operator_bindings
            operator = group_info.get('operator')
            if not operator:
                chat = message.chat
                if chat and chat.assigned_operator:
                    operator = chat.assigned_operator
            if not operator:
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
            
            # Enterprise: notify group if experience has one (operator responds from group)
            reservation.status = 'operator_notified'
            reservation.save(update_fields=['status'])
            try:
                GroupNotificationService.send_reservation_notification(reservation)
            except Exception as e:
                logger.error(f"Error sending reservation to group (no operator): {e}")
            
            # Enterprise: send waiting message to customer even without operator
            try:
                customer_phone = WhatsAppWebService.clean_phone_number(message.phone)
                chat_id = getattr(message.chat, 'chat_id', None) if message.chat else None
                waiting_message = GroupNotificationService.format_waiting_message(reservation)
                service = WhatsAppWebService()
                service.send_message(customer_phone, waiting_message, chat_id=chat_id)
                logger.info(f"✅ Sent waiting message to customer {customer_phone} (no operator)")
            except Exception as e:
                logger.error(f"Error sending waiting message to customer (no operator): {e}")
            
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
        
        # Send waiting message to customer
        try:
            customer_phone = WhatsAppWebService.clean_phone_number(message.phone)
            waiting_message = GroupNotificationService.format_waiting_message(reservation)
            service = WhatsAppWebService()
            service.send_message(customer_phone, waiting_message)
            logger.info(f"✅ Sent waiting message to customer {customer_phone}")
        except Exception as e:
            logger.error(f"Error sending waiting message to customer: {e}")
        
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
            sender_phone=data.get('sender_phone'),
            media_type=data.get('media_type') or None,
            reply_to_whatsapp_id=data.get('reply_to_whatsapp_id') or None,
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
        logger.info(
            f"Message content_len={len(message.content or '')} parsed_reservation_code={reservation_code} "
            f"content_preview={repr((message.content or '')[:100])}"
        )
        if reservation_code:
            try:
                logger.info(f"📩 Processing reservation code: {reservation_code}")
                reservation = MessageProcessor.process_reservation_code(message, reservation_code)
                if reservation:
                    return {
                        'status': 'reservation_created',
                        'message_id': str(message.id),
                        'reservation_id': str(reservation.id)
                    }
                # Code was extracted but processing failed - notify customer
                MessageProcessor._send_code_error_message(message, reservation_code)
            except Exception as e:
                logger.exception(f"Error processing reservation code {reservation_code}: {e}")
                MessageProcessor._send_code_error_message(message, reservation_code)
        
        # Check for operator response (1/2, sí/no, etc.) - from group, use sender_phone
        text = data.get('text', '').strip().lower()
        sender_phone = data.get('sender_phone', '')
        if text in ['1', '2', 'sí', 'si', 'yes', 'no', 'confirmar', 'rechazar'] and sender_phone:
            operator_data = {
                'text': text,
                'phone': sender_phone,
                'chat_id': data.get('chat_id'),
            }
            operator_result = MessageProcessor._process_operator_response(operator_data)
            if operator_result.get('status') in ['availability_confirmed', 'rejected']:
                return {
                    'status': 'operator_response_processed',
                    'message_id': str(message.id),
                    'reservation_status': operator_result.get('status')
                }

        # Check for customer confirmation (SI/sí/yes) - free reservation, from customer
        if text in ['sí', 'si', 'yes', 'confirmar']:
            customer_result = MessageProcessor._process_customer_confirmation(message, data)
            if customer_result:
                return customer_result

        return {
            'status': 'processed',
            'message_id': str(message.id)
        }
    
    @staticmethod
    def _process_operator_response(data: Dict) -> Dict:
        """
        Process operator response (1=confirm, 2=reject).
        Enterprise: match by group first (when message from group), then by operator phone.
        """
        from apps.whatsapp.models import ExperienceGroupBinding
        
        text = data.get('text', '').strip().lower()
        is_confirm = text in ['1', 'sí', 'si', 'yes', 'confirmar']
        phone = data.get('phone', '')
        chat_id = data.get('chat_id', '')
        
        reservation = None
        operator = None
        
        # 1) Group-based: message from group → find reservation by experience's group
        if chat_id and '@g.us' in str(chat_id):
            group_chat = WhatsAppChat.objects.filter(chat_id=chat_id, type='group').first()
            if group_chat:
                exp_ids = list(
                    ExperienceGroupBinding.objects.filter(
                        whatsapp_group=group_chat,
                        is_active=True
                    ).values_list('experience_id', flat=True)
                )
                if exp_ids:
                    reservation = WhatsAppReservationRequest.objects.filter(
                        experience_id__in=exp_ids,
                        status='operator_notified'
                    ).order_by('-created_at').first()
                    if reservation:
                        operator = reservation.operator
        
        # 2) Operator-by-phone fallback
        if not reservation and phone:
            operator = (
                TourOperator.objects.filter(whatsapp_number=phone).first()
                or TourOperator.objects.filter(contact_phone=phone).first()
            )
            if operator:
                reservation = WhatsAppReservationRequest.objects.filter(
                    operator=operator,
                    status='operator_notified'
                ).order_by('-created_at').first()
        
        if not reservation:
            logger.info(f"No pending reservation found for chat/operator (chat_id={chat_id}, phone={phone})")
            return {'status': 'no_pending_reservation'}
        
        # Operator confirmed availability (1) or rejected (2)
        op_name = operator.name if operator else 'grupo'
        if is_confirm:
            ReservationHandler.confirm_availability(reservation)
            logger.info(f"Reservation {reservation.id} availability confirmed by {op_name}")
            return {
                'status': 'availability_confirmed',
                'confirmed': True,
                'reservation_id': str(reservation.id)
            }
        else:
            ReservationHandler.reject_reservation(reservation)
            logger.info(f"Reservation {reservation.id} rejected by {op_name}")
        return {
            'status': 'rejected',
            'confirmed': False,
            'reservation_id': str(reservation.id)
        }

    @staticmethod
    def _send_code_error_message(message: WhatsAppMessage, reservation_code: str) -> None:
        """
        Send a helpful message to the customer when reservation code processing fails.
        """
        try:
            customer_phone = WhatsAppWebService.clean_phone_number(message.phone)
            if not customer_phone:
                logger.warning("Cannot send code error message: no phone number")
                return
            msg = (
                f"Hola. Recibimos su mensaje con el código {reservation_code}, pero no pudimos procesarlo. "
                "Puede que el código haya expirado o no exista. Por favor, genere un nuevo código desde la página de la experiencia y envíe el mensaje nuevamente."
            )
            service = WhatsAppWebService()
            service.send_message(customer_phone, msg)
            logger.info(f"Sent code error message to customer {customer_phone} for code {reservation_code}")
        except Exception as e:
            logger.error(f"Failed to send code error message: {e}")

    @staticmethod
    def _process_customer_confirmation(message, data: Dict) -> Optional[Dict]:
        """
        Process customer "SI" for free reservation confirmation.
        Returns result dict if processed, None otherwise.
        """
        customer_phone_raw = data.get('phone', '') or (message.phone if message else '')
        if not customer_phone_raw:
            return None
        customer_phone = WhatsAppWebService.clean_phone_number(customer_phone_raw)
        if not customer_phone:
            return None

        # Find reservation in availability_confirmed (free) for this customer
        reservations = WhatsAppReservationRequest.objects.filter(
            status='availability_confirmed'
        ).select_related('whatsapp_message').order_by('-created_at')

        for reservation in reservations:
            msg_phone = WhatsAppWebService.clean_phone_number(
                reservation.whatsapp_message.phone
            )
            if msg_phone == customer_phone:
                total = ReservationHandler._get_total_from_checkout(reservation)
                if total <= 0:
                    ReservationHandler.confirm_reservation(reservation)
                    logger.info(f"Customer confirmed free reservation {reservation.id}")
                    return {
                        'status': 'customer_confirmed',
                        'message_id': str(message.id),
                        'reservation_id': str(reservation.id)
                    }
                break
        return None

