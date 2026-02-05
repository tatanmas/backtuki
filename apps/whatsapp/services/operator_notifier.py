"""Operator notification service."""
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
from apps.whatsapp.models import TourOperator
import secrets
import string


class OperatorNotifier:
    """Send notifications to tour operators."""
    
    @staticmethod
    def generate_confirmation_token(length=6):
        """Generate a short confirmation token."""
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))
    
    @staticmethod
    def notify_operator(reservation):
        """
        Send notification to operator about new reservation.
        
        Args:
            reservation: WhatsAppReservationRequest instance
            
        Returns:
            bool: True if notification sent successfully
        """
        operator = reservation.operator
        experience = reservation.experience
        
        # Generate confirmation token
        token = OperatorNotifier.generate_confirmation_token()
        reservation.confirmation_token = token
        reservation.save()
        
        # Build message - formal tone, no emojis
        message = f"""Nueva solicitud de reserva

Tour: {experience.title if experience else reservation.tour_code}
Codigo: {reservation.tour_code}
Cliente: {reservation.whatsapp_message.phone}
Pasajeros: {reservation.passengers or 1}
Estado: Pendiente de confirmacion de disponibilidad

Responda 1 para confirmar disponibilidad, 2 para rechazar.
Token: {token}"""
        
        # Get operator phone number
        operator_phone = operator.whatsapp_number or operator.contact_phone
        
        if not operator_phone:
            return False
        
        # Send message
        try:
            whatsapp_service = WhatsAppWebService()
            whatsapp_service.send_message(operator_phone, message)
            return True
        except Exception as e:
            print(f"Error notifying operator: {e}")
            return False
    
    @staticmethod
    def notify_customer_confirmed(reservation):
        """Notify customer that reservation is confirmed."""
        customer_phone = reservation.whatsapp_message.phone
        experience = reservation.experience
        
        message = f"""¡Excelente! Tu reserva para el tour {experience.title if experience else reservation.tour_code} ha sido confirmada.

Pasajeros: {reservation.passengers or 1}
Te contactaremos pronto con los detalles finales."""
        
        try:
            whatsapp_service = WhatsAppWebService()
            whatsapp_service.send_message(customer_phone, message)
            return True
        except Exception as e:
            print(f"Error notifying customer: {e}")
            return False
    
    @staticmethod
    def notify_customer_rejected(reservation):
        """Notify customer that reservation is rejected."""
        customer_phone = reservation.whatsapp_message.phone
        experience = reservation.experience
        
        message = f"""Lo sentimos, tu solicitud para el tour {experience.title if experience else reservation.tour_code} no pudo ser confirmada en este momento.

Por favor intenta con otra fecha o contacta directamente con el organizador."""
        
        try:
            whatsapp_service = WhatsAppWebService()
            whatsapp_service.send_message(customer_phone, message)
            return True
        except Exception as e:
            print(f"Error notifying customer: {e}")
            return False

