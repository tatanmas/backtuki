"""Reservation handling logic."""
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
import uuid
import logging

from apps.whatsapp.models import WhatsAppReservationRequest
from apps.experiences.models import Experience, ExperienceReservation, TourInstance

logger = logging.getLogger(__name__)


class ReservationHandler:
    """Handle reservation requests."""
    
    DEFAULT_TIMEOUT_MINUTES = 30
    
    @staticmethod
    def create_reservation(message, tour_code, passengers, operator, experience):
        """
        Create a reservation request.
        
        Args:
            message: WhatsAppMessage instance
            tour_code: Extracted tour code
            passengers: Number of passengers
            operator: TourOperator instance
            experience: Experience instance
            
        Returns:
            WhatsAppReservationRequest instance
        """
        reservation = WhatsAppReservationRequest.objects.create(
            whatsapp_message=message,
            tour_code=tour_code,
            passengers=passengers,
            operator=operator,
            experience=experience,
            status='processing',
            timeout_at=timezone.now() + timedelta(minutes=ReservationHandler.DEFAULT_TIMEOUT_MINUTES)
        )
        
        return reservation
    
    @staticmethod
    def mark_operator_notified(reservation):
        """Mark reservation as operator notified and send notification."""
        reservation.status = 'operator_notified'
        reservation.save()
        
        # Send notification to group or operator
        GroupNotificationService.send_reservation_notification(reservation)
    
    @staticmethod
    def confirm_reservation(reservation):
        """Confirm a reservation and create ExperienceReservation."""
        with transaction.atomic():
            reservation.status = 'confirmed'
            reservation.save()
            
            # Notify customer
            GroupNotificationService.send_customer_confirmation(reservation)
            
            # Obtener código vinculado si existe
            # La relación es: WhatsAppReservationCode.linked_reservation -> WhatsAppReservationRequest
            # Entonces buscamos el código que tiene este reservation como linked_reservation
            from apps.whatsapp.models import WhatsAppReservationCode
            code_obj = WhatsAppReservationCode.objects.filter(
                linked_reservation=reservation
            ).first()
            
            if code_obj and code_obj.checkout_data:
                checkout_data = code_obj.checkout_data
                experience = reservation.experience
                
                if not experience:
                    logger.error(f"Reservation {reservation.id} has no experience")
                    return
                
                # Buscar TourInstance basado en fecha del checkout
                instance = None
                checkout_date = checkout_data.get('date')
                checkout_time = checkout_data.get('time')
                
                if checkout_date:
                    # Buscar instancia que coincida con la fecha
                    from datetime import datetime
                    try:
                        if isinstance(checkout_date, str):
                            # Parsear fecha (formato YYYY-MM-DD)
                            date_obj = datetime.strptime(checkout_date, '%Y-%m-%d').date()
                        else:
                            date_obj = checkout_date
                        
                        # Buscar instancia activa para esa fecha
                        instances = TourInstance.objects.filter(
                            experience=experience,
                            start_datetime__date=date_obj,
                            status='active'
                        )
                        
                        if checkout_time:
                            # Si hay hora, buscar la más cercana
                            from datetime import time as dt_time
                            if isinstance(checkout_time, str):
                                time_obj = datetime.strptime(checkout_time, '%H:%M').time()
                            else:
                                time_obj = checkout_time
                            
                            # Buscar instancia con hora más cercana
                            instance = min(
                                instances,
                                key=lambda i: abs((i.start_datetime.time() - time_obj).total_seconds()),
                                default=None
                            )
                        
                        if not instance:
                            instance = instances.first()
                    except Exception as e:
                        logger.warning(f"Error parsing date/time: {e}")
                        instance = None
                
                # Si no hay instancia, usar la primera disponible futura
                if not instance:
                    instance = TourInstance.objects.filter(
                        experience=experience,
                        start_datetime__gt=timezone.now(),
                        status='active'
                    ).order_by('start_datetime').first()
                
                if instance:
                    # Crear ExperienceReservation
                    reservation_id = f"EXP-{uuid.uuid4().hex[:12].upper()}"
                    participants = checkout_data.get('participants', {})
                    pricing = checkout_data.get('pricing', {})
                    contact = checkout_data.get('contact', {})
                    
                    experience_reservation = ExperienceReservation.objects.create(
                        reservation_id=reservation_id,
                        experience=experience,
                        instance=instance,
                        status='pending',  # Pendiente de pago
                        adult_count=participants.get('adults', 1),
                        child_count=participants.get('children', 0),
                        infant_count=participants.get('infants', 0),
                        first_name=contact.get('first_name', ''),
                        last_name=contact.get('last_name', ''),
                        email=contact.get('email', ''),
                        phone=reservation.whatsapp_message.phone,
                        subtotal=float(pricing.get('subtotal', 0)),
                        service_fee=float(pricing.get('service_fee', 0)),
                        discount=float(pricing.get('discount', 0)),
                        total=float(pricing.get('total', 0)),
                        currency=pricing.get('currency', 'CLP'),
                        pricing_details=pricing.get('breakdown', {}),
                    )
                    
                    # Vincular
                    reservation.linked_experience_reservation = experience_reservation
                    reservation.save()
                    
                    logger.info(f"Created ExperienceReservation {reservation_id} for WhatsApp reservation {reservation.id}")
                    return experience_reservation
                else:
                    logger.warning(f"No TourInstance found for reservation {reservation.id}")
                    return None
    
    @staticmethod
    def reject_reservation(reservation):
        """Reject a reservation."""
        reservation.status = 'rejected'
        reservation.save()
        
        # Notify customer
        GroupNotificationService.send_customer_rejection(reservation)
    
    @staticmethod
    def check_timeouts():
        """Check and mark expired reservations."""
        now = timezone.now()
        expired = WhatsAppReservationRequest.objects.filter(
            status='operator_notified',
            timeout_at__lt=now
        )
        
        for reservation in expired:
            reservation.status = 'timeout'
            reservation.save()
        
        return expired.count()

