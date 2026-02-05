"""Reservation handling logic."""
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from django.db import transaction
import uuid
import logging

from apps.whatsapp.models import WhatsAppReservationRequest, WhatsAppReservationCode
from apps.whatsapp.services.group_notification_service import GroupNotificationService
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
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
    def _get_total_from_checkout(reservation) -> float:
        """Get total price from linked code's checkout_data."""
        code_obj = WhatsAppReservationCode.objects.filter(
            linked_reservation=reservation
        ).first()
        if not code_obj or not code_obj.checkout_data:
            return 0.0
        pricing = code_obj.checkout_data.get('pricing', {}) or {}
        try:
            return float(pricing.get('total', 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _build_payment_url(reservation) -> str:
        """Build frontend URL for payment (experience checkout with code)."""
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080').rstrip('/')
        exp = reservation.experience
        if not exp:
            return f"{frontend_url}/checkout/experiences"
        return f"{frontend_url}/checkout/experiences/{exp.slug}?codigo={reservation.tour_code}"

    @staticmethod
    def _create_experience_reservation_if_needed(reservation) -> bool:
        """
        Create ExperienceReservation and link to WhatsAppReservationRequest.
        Required for payment link to work (reservation-by-code returns experience_reservation_id).
        Returns True if created, False otherwise.
        """
        if reservation.linked_experience_reservation_id:
            return False
        code_obj = WhatsAppReservationCode.objects.filter(linked_reservation=reservation).first()
        if not code_obj or not code_obj.checkout_data:
            return False
        exp_res = ReservationHandler._create_and_link_experience_reservation(reservation, code_obj)
        return exp_res is not None

    @staticmethod
    def _create_and_link_experience_reservation(reservation, code_obj):
        """Create ExperienceReservation from checkout_data and link to reservation."""
        checkout_data = code_obj.checkout_data
        experience = reservation.experience
        if not experience:
            return None
        from datetime import datetime
        instance = None
        checkout_date = checkout_data.get('date')
        checkout_time = checkout_data.get('time')
        if checkout_date:
            try:
                date_obj = datetime.strptime(checkout_date, '%Y-%m-%d').date() if isinstance(checkout_date, str) else checkout_date
                instances = TourInstance.objects.filter(
                    experience=experience, start_datetime__date=date_obj, status='active'
                )
                if checkout_time:
                    time_obj = datetime.strptime(checkout_time, '%H:%M').time() if isinstance(checkout_time, str) else checkout_time
                    def _time_seconds(t):
                        return (t.hour * 3600) + (t.minute * 60) + t.second
                    target_sec = _time_seconds(time_obj)
                    instance = min(
                        instances,
                        key=lambda i: abs(_time_seconds(i.start_datetime.time()) - target_sec),
                        default=None
                    )
                if not instance:
                    instance = instances.first()
            except Exception as e:
                logger.warning(f"Error parsing date/time: {e}")
        if not instance:
            instance = TourInstance.objects.filter(
                experience=experience, start_datetime__gt=timezone.now(), status='active'
            ).order_by('start_datetime').first()
        if not instance:
            return None
        participants = checkout_data.get('participants', {})
        pricing = checkout_data.get('pricing', {})
        contact = dict(checkout_data.get('contact') or checkout_data.get('customer') or {})
        if contact.get('name') and not contact.get('first_name'):
            name_parts = str(contact['name']).strip().split(None, 1)
            contact['first_name'] = name_parts[0]
            contact['last_name'] = name_parts[1] if len(name_parts) > 1 else ''
        with transaction.atomic():
            reservation_id = f"EXP-{uuid.uuid4().hex[:12].upper()}"
            experience_reservation = ExperienceReservation.objects.create(
                reservation_id=reservation_id,
                experience=experience,
                instance=instance,
                status='pending',
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
            reservation.linked_experience_reservation = experience_reservation
            reservation.save(update_fields=['linked_experience_reservation'])
            logger.info(f"Created ExperienceReservation {reservation_id} for WhatsApp reservation {reservation.id}")
            return experience_reservation

    @staticmethod
    def confirm_availability(reservation):
        """
        Operator confirmed availability. Send appropriate message to customer.
        - If paid (total > 0): create ExperienceReservation, send availability msg + payment link
        - If free: send message asking customer to reply SI to confirm
        """
        reservation.status = 'availability_confirmed'
        reservation.save()

        code_obj = WhatsAppReservationCode.objects.filter(
            linked_reservation=reservation
        ).first()
        total = ReservationHandler._get_total_from_checkout(reservation)
        customer_phone = WhatsAppWebService.clean_phone_number(
            reservation.whatsapp_message.phone
        )
        service = WhatsAppWebService()

        if total > 0:
            # Paid: create ExperienceReservation first (needed for payment link / reservation-by-code)
            ReservationHandler._create_experience_reservation_if_needed(reservation)
            # Send availability message, then payment link
            msg_avail = GroupNotificationService.format_availability_confirmed_message(reservation)
            service.send_message(customer_phone, msg_avail)
            payment_url = ReservationHandler._build_payment_url(reservation)
            reservation.payment_link = payment_url
            reservation.payment_link_sent_at = timezone.now()
            reservation.save()
            msg_payment = GroupNotificationService.format_payment_link_message(
                reservation, payment_url
            )
            service.send_message(customer_phone, msg_payment)
            logger.info(f"Sent availability + payment link for reservation {reservation.id}")
        else:
            # Free: ask customer to reply SI to confirm
            msg = GroupNotificationService.format_confirm_free_message(reservation)
            service.send_message(customer_phone, msg)
            logger.info(f"Sent confirm-free message for reservation {reservation.id}")

    @staticmethod
    def confirm_reservation(reservation):
        """Confirm a free reservation: create ExperienceReservation and notify customer."""
        with transaction.atomic():
            reservation.status = 'confirmed'
            reservation.save()
            GroupNotificationService.send_customer_confirmation(reservation)
            code_obj = WhatsAppReservationCode.objects.filter(linked_reservation=reservation).first()
            if code_obj:
                return ReservationHandler._create_and_link_experience_reservation(reservation, code_obj)
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

