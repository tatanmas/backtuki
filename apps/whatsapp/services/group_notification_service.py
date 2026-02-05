"""
Service for sending notifications to WhatsApp groups.

This service handles:
- Sending reservation notifications to groups
- Determining which group to use for an experience
- Formatting notification messages using templates
- Sending payment links and confirmations
"""
import logging
from typing import Optional, Dict
from django.utils import timezone

from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
from apps.whatsapp.services.experience_operator_service import ExperienceOperatorService
from apps.whatsapp.services.template_service import TemplateService
from apps.whatsapp.models import WhatsAppReservationRequest, WhatsAppReservationCode
from apps.experiences.models import Experience

logger = logging.getLogger(__name__)


class GroupNotificationService:
    """Service for sending notifications to WhatsApp groups."""
    
    @staticmethod
    def _get_code_obj(reservation: WhatsAppReservationRequest) -> Optional[WhatsAppReservationCode]:
        """Get the WhatsAppReservationCode for a reservation."""
        try:
            return WhatsAppReservationCode.objects.filter(
                code=reservation.tour_code
            ).first()
        except Exception:
            return None
    
    @staticmethod
    def format_reservation_notification(reservation: WhatsAppReservationRequest) -> str:
        """
        Format a reservation notification message using templates.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            Formatted message string
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_reservation_request(reservation, code_obj)
    
    @staticmethod
    def format_confirmation_message(
        reservation: WhatsAppReservationRequest,
        payment_link: Optional[str] = None
    ) -> str:
        """
        Format a confirmation message for the customer.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            payment_link: Optional payment link to include
            
        Returns:
            Formatted message string
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_customer_confirmation(reservation, code_obj, payment_link)
    
    @staticmethod
    def format_rejection_message(reservation: WhatsAppReservationRequest) -> str:
        """
        Format a rejection message for the customer.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            Formatted message string
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_customer_rejection(reservation, code_obj)
    
    @staticmethod
    def format_waiting_message(reservation: WhatsAppReservationRequest) -> str:
        """
        Format a waiting message for the customer.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            Formatted message string
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_customer_waiting(reservation, code_obj)
    
    @staticmethod
    def format_payment_link_message(
        reservation: WhatsAppReservationRequest,
        payment_link: str
    ) -> str:
        """
        Format a payment link message for the customer.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            payment_link: Payment link URL
            
        Returns:
            Formatted message string
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_payment_link(reservation, payment_link, code_obj)
    
    @staticmethod
    def format_payment_confirmed_message(reservation: WhatsAppReservationRequest) -> str:
        """
        Format a payment confirmed message for the customer.
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_payment_confirmed(reservation, code_obj)
    
    @staticmethod
    def format_ticket_message(reservation: WhatsAppReservationRequest) -> str:
        """
        Format a ticket info message for the customer.
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_ticket_info(reservation, code_obj)
    
    @staticmethod
    def format_reminder_message(reservation: WhatsAppReservationRequest) -> str:
        """
        Format a reminder message for the operator.
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_reminder(reservation, code_obj)

    @staticmethod
    def format_availability_confirmed_message(reservation: WhatsAppReservationRequest) -> str:
        """
        Format availability confirmed message for the customer.
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_customer_availability_confirmed(reservation, code_obj)

    @staticmethod
    def format_confirm_free_message(reservation: WhatsAppReservationRequest) -> str:
        """
        Format message asking customer to confirm free reservation.
        """
        code_obj = GroupNotificationService._get_code_obj(reservation)
        return TemplateService.render_customer_confirm_free(reservation, code_obj)
    
    @staticmethod
    def get_group_for_experience(experience: Experience) -> Optional[Dict]:
        """
        Get the WhatsApp group for an experience.
        
        Args:
            experience: Experience instance
            
        Returns:
            Dict with group info or None
        """
        return ExperienceOperatorService.get_experience_whatsapp_group(experience)
    
    @staticmethod
    def send_reservation_notification(reservation: WhatsAppReservationRequest) -> bool:
        """
        Send reservation notification to the appropriate group or operator.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            True if notification sent successfully
        """
        experience = reservation.experience
        if not experience:
            logger.warning(f"Reservation {reservation.id} has no experience")
            return False
        
        # Get group for experience
        group_info = GroupNotificationService.get_group_for_experience(experience)
        
        if not group_info:
            # Fallback to operator direct notification
            operator = reservation.operator
            if not operator:
                logger.warning(f"No group or operator for reservation {reservation.id}")
                return False
            
            from apps.whatsapp.services.operator_notifier import OperatorNotifier
            return OperatorNotifier.notify_operator(reservation)
        
        # Send to group
        group_id = group_info.get('chat_id')
        if not group_id:
            logger.warning(f"Group info missing chat_id for reservation {reservation.id}")
            return False
        
        try:
            service = WhatsAppWebService()
            message = GroupNotificationService.format_reservation_notification(reservation)
            service.send_message('', message, group_id=group_id)
            logger.info(f"✅ Sent reservation notification to group {group_id} for reservation {reservation.id}")
            return True
        except Exception as e:
            logger.error(f"Error sending notification to group {group_id}: {e}")
            return False
    
    @staticmethod
    def send_customer_confirmation(reservation: WhatsAppReservationRequest) -> bool:
        """
        Send confirmation message and optional ticket image to customer.

        Args:
            reservation: WhatsAppReservationRequest instance

        Returns:
            True if at least the text message was sent successfully
        """
        customer_phone = WhatsAppWebService.clean_phone_number(
            reservation.whatsapp_message.phone
        )
        message = GroupNotificationService.format_confirmation_message(reservation)
        service = WhatsAppWebService()

        try:
            service.send_message(customer_phone, message)
            logger.info(f"Sent confirmation to customer {customer_phone} for reservation {reservation.id}")
        except Exception as e:
            logger.error(f"Error sending confirmation to customer {customer_phone}: {e}")
            return False

        try:
            from apps.whatsapp.services.ticket_image_service import TicketImageService
            ticket_b64 = TicketImageService.generate_ticket_base64(reservation)
            if ticket_b64:
                service.send_media(
                    customer_phone,
                    media_base64=ticket_b64,
                    mimetype='image/png',
                    filename='comprobante-reserva.png',
                    caption='Comprobante de su reserva.'
                )
                logger.info(f"Sent ticket image to customer {customer_phone}")
        except Exception as e:
            logger.warning(f"Could not send ticket image (text sent): {e}")

        return True
    
    @staticmethod
    def send_customer_rejection(reservation: WhatsAppReservationRequest) -> bool:
        """
        Send rejection message to customer.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            True if message sent successfully
        """
        customer_phone = WhatsAppWebService.clean_phone_number(
            reservation.whatsapp_message.phone
        )
        message = GroupNotificationService.format_rejection_message(reservation)
        
        try:
            service = WhatsAppWebService()
            service.send_message(customer_phone, message)
            logger.info(f"✅ Sent rejection to customer {customer_phone} for reservation {reservation.id}")
            return True
        except Exception as e:
            logger.error(f"Error sending rejection to customer {customer_phone}: {e}")
            return False

