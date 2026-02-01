"""
Service for sending notifications to WhatsApp groups.

This service handles:
- Sending reservation notifications to groups
- Determining which group to use for an experience
- Formatting notification messages
"""
import logging
from typing import Optional, Dict
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
from apps.whatsapp.services.experience_operator_service import ExperienceOperatorService
from apps.whatsapp.models import WhatsAppReservationRequest
from apps.experiences.models import Experience

logger = logging.getLogger(__name__)


class GroupNotificationService:
    """Service for sending notifications to WhatsApp groups."""
    
    @staticmethod
    def format_reservation_notification(reservation: WhatsAppReservationRequest) -> str:
        """
        Format a reservation notification message.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            Formatted message string
        """
        experience = reservation.experience
        tour_name = experience.title if experience else reservation.tour_code
        
        message = f"""🔔 NUEVA RESERVA
Tour: {tour_name}
Código: {reservation.tour_code}
Cliente: +{reservation.whatsapp_message.phone}
Pasajeros: {reservation.passengers or 1}
Estado: Pendiente confirmación

Responde: 1=Confirmar, 2=Rechazar"""
        
        if reservation.confirmation_token:
            message += f"\nToken: {reservation.confirmation_token}"
        
        return message
    
    @staticmethod
    def format_confirmation_message(reservation: WhatsAppReservationRequest) -> str:
        """
        Format a confirmation message for the customer.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            Formatted message string
        """
        experience = reservation.experience
        tour_name = experience.title if experience else reservation.tour_code
        
        return f"""¡Excelente! Tu reserva para el tour {tour_name} ha sido confirmada.

Pasajeros: {reservation.passengers or 1}
Te contactaremos pronto con los detalles finales."""
    
    @staticmethod
    def format_rejection_message(reservation: WhatsAppReservationRequest) -> str:
        """
        Format a rejection message for the customer.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            Formatted message string
        """
        experience = reservation.experience
        tour_name = experience.title if experience else reservation.tour_code
        
        return f"""Lo sentimos, tu solicitud para el tour {tour_name} no pudo ser confirmada en este momento.

Por favor intenta con otra fecha o contacta directamente con el organizador."""
    
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
        Send confirmation message to customer.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            True if message sent successfully
        """
        customer_phone = reservation.whatsapp_message.phone
        message = GroupNotificationService.format_confirmation_message(reservation)
        
        try:
            service = WhatsAppWebService()
            service.send_message(customer_phone, message)
            logger.info(f"✅ Sent confirmation to customer {customer_phone} for reservation {reservation.id}")
            return True
        except Exception as e:
            logger.error(f"Error sending confirmation to customer {customer_phone}: {e}")
            return False
    
    @staticmethod
    def send_customer_rejection(reservation: WhatsAppReservationRequest) -> bool:
        """
        Send rejection message to customer.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            True if message sent successfully
        """
        customer_phone = reservation.whatsapp_message.phone
        message = GroupNotificationService.format_rejection_message(reservation)
        
        try:
            service = WhatsAppWebService()
            service.send_message(customer_phone, message)
            logger.info(f"✅ Sent rejection to customer {customer_phone} for reservation {reservation.id}")
            return True
        except Exception as e:
            logger.error(f"Error sending rejection to customer {customer_phone}: {e}")
            return False

