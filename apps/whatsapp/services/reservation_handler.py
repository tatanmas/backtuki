"""Reservation handling logic (experience and accommodation)."""
from django.utils import timezone
from django.conf import settings
from datetime import timedelta, datetime
from django.db import transaction
import uuid
import logging

from core.flow_logger import FlowLogger
from apps.whatsapp.models import WhatsAppReservationRequest, WhatsAppReservationCode
from apps.whatsapp.services.group_notification_service import GroupNotificationService
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
from apps.experiences.models import Experience, ExperienceReservation, TourInstance
from apps.accommodations.models import AccommodationReservation

logger = logging.getLogger(__name__)


class ReservationHandler:
    """Handle reservation requests (experience or accommodation)."""

    DEFAULT_TIMEOUT_MINUTES = 30

    @staticmethod
    def start_flow_for_code(code_obj):
        """
        🚀 ENTERPRISE: Start a platform flow when a reservation code is generated.
        So superadmin sees the intent even if the customer never sends the WhatsApp message.
        """
        if not code_obj:
            return
        try:
            flow_type = 'accommodation_booking' if code_obj.accommodation_id else 'experience_booking'
            experience = getattr(code_obj, 'experience', None)
            accommodation = getattr(code_obj, 'accommodation', None)
            organizer = None
            if experience:
                organizer = getattr(experience, 'organizer', None)
            elif accommodation:
                organizer = getattr(accommodation, 'organizer', None)
            flow = FlowLogger.start_flow(
                flow_type,
                experience=experience,
                accommodation=accommodation,
                organizer=organizer,
                user=None,
                metadata={
                    'source': 'whatsapp_code_generated',
                    'code': code_obj.code,
                    'code_id': str(code_obj.id),
                },
            )
            if flow and flow.flow:
                code_obj.flow = flow.flow
                code_obj.save(update_fields=['flow'])
                flow.log_event(
                    'RESERVATION_REQUESTED',
                    source='api',
                    status='success',
                    message='Código de reserva generado (pendiente envío por WhatsApp)',
                    metadata={'code': code_obj.code},
                )
        except Exception as e:
            logger.warning("FlowLogger start_flow_for_code: %s", e)

    @staticmethod
    def ensure_flow_and_log_request(reservation):
        """
        Ensure the WhatsAppReservationRequest has a flow and log WHATSAPP_REQUEST_RECEIVED.
        If the linked code already has a flow (from code generation), reuse it; otherwise start a new flow.
        """
        if reservation.flow_id:
            try:
                flow = FlowLogger.from_flow_id(reservation.flow_id)
                if flow:
                    flow.log_event(
                        'WHATSAPP_REQUEST_RECEIVED',
                        source='api',
                        status='success',
                        message=f"WhatsApp message received (code {reservation.tour_code})",
                        metadata={'whatsapp_reservation_id': str(reservation.id)},
                    )
            except Exception as e:
                logger.warning("FlowLogger ensure_flow_and_log_request (existing): %s", e)
            return
        code_obj = WhatsAppReservationCode.objects.filter(linked_reservation=reservation).first()
        if code_obj and code_obj.flow_id:
            reservation.flow_id = code_obj.flow_id
            reservation.save(update_fields=['flow'])
            try:
                flow = FlowLogger.from_flow_id(reservation.flow_id)
                if flow:
                    flow.log_event(
                        'WHATSAPP_REQUEST_RECEIVED',
                        source='api',
                        status='success',
                        message=f"Mensaje WhatsApp recibido (código {reservation.tour_code})",
                        metadata={'whatsapp_reservation_id': str(reservation.id)},
                    )
            except Exception as e:
                logger.warning("FlowLogger ensure_flow_and_log_request (from code): %s", e)
            return
        try:
            flow_type = 'accommodation_booking' if reservation.accommodation_id else 'experience_booking'
            experience = getattr(reservation, 'experience', None)
            accommodation = getattr(reservation, 'accommodation', None)
            organizer = None
            if experience:
                organizer = getattr(experience, 'organizer', None)
            elif accommodation:
                organizer = getattr(accommodation, 'organizer', None)
            flow = FlowLogger.start_flow(
                flow_type,
                experience=experience,
                accommodation=accommodation,
                organizer=organizer,
                user=None,
                metadata={
                    'source': 'whatsapp',
                    'whatsapp_reservation_id': str(reservation.id),
                    'tour_code': reservation.tour_code,
                },
            )
            if flow and flow.flow:
                reservation.flow = flow.flow
                reservation.save(update_fields=['flow'])
                flow.log_event(
                    'WHATSAPP_REQUEST_RECEIVED',
                    source='api',
                    status='success',
                    message=f"WhatsApp reservation request received (code {reservation.tour_code})",
                    metadata={'whatsapp_reservation_id': str(reservation.id)},
                )
        except Exception as e:
            logger.warning("FlowLogger ensure_flow_and_log_request (new): %s", e)

    @staticmethod
    def create_reservation(message, tour_code, passengers, operator, experience=None, accommodation=None, existing_flow=None):
        """
        Create a WhatsAppReservationRequest (experience or accommodation).
        Starts platform flow (or reuses existing_flow from code) and logs WHATSAPP_REQUEST_RECEIVED.

        One of experience or accommodation must be set.
        If existing_flow is provided (from code_obj.flow when message is received), reuse it instead of creating a new flow.
        """
        reservation = WhatsAppReservationRequest.objects.create(
            whatsapp_message=message,
            tour_code=tour_code,
            passengers=passengers,
            operator=operator,
            experience=experience,
            accommodation=accommodation,
            status="processing",
            timeout_at=timezone.now() + timedelta(minutes=ReservationHandler.DEFAULT_TIMEOUT_MINUTES),
        )
        # 🚀 ENTERPRISE: Use existing flow from code or start new one
        try:
            if existing_flow:
                reservation.flow = existing_flow
                reservation.save(update_fields=['flow'])
                flow = FlowLogger.from_flow_id(existing_flow.id)
                if flow:
                    flow.log_event(
                        'WHATSAPP_REQUEST_RECEIVED',
                        source='api',
                        status='success',
                        message=f"WhatsApp reservation request received (code {tour_code})",
                        metadata={'whatsapp_reservation_id': str(reservation.id)},
                    )
            else:
                flow_type = 'accommodation_booking' if accommodation else 'experience_booking'
                organizer = None
                if experience:
                    organizer = getattr(experience, 'organizer', None)
                elif accommodation:
                    organizer = getattr(accommodation, 'organizer', None)
                flow = FlowLogger.start_flow(
                    flow_type,
                    experience=experience,
                    accommodation=accommodation,
                    organizer=organizer,
                    user=None,
                    metadata={
                        'source': 'whatsapp',
                        'whatsapp_reservation_id': str(reservation.id),
                        'tour_code': tour_code,
                        'passengers': passengers,
                    },
                )
                if flow and flow.flow:
                    reservation.flow = flow.flow
                    reservation.save(update_fields=['flow'])
                    flow.log_event(
                        'WHATSAPP_REQUEST_RECEIVED',
                        source='api',
                        status='success',
                        message=f"WhatsApp reservation request received (code {tour_code})",
                        metadata={'whatsapp_reservation_id': str(reservation.id)},
                    )
        except Exception as e:
            logger.warning("FlowLogger start_flow on create_reservation: %s", e)
        return reservation
    
    @staticmethod
    def mark_operator_notified(reservation):
        """Mark reservation as operator notified and send notification."""
        reservation.status = 'operator_notified'
        reservation.save()

        # 🚀 ENTERPRISE: Log step in platform flow
        if reservation.flow_id:
            try:
                flow = FlowLogger.from_flow_id(reservation.flow_id)
                if flow:
                    flow.log_event(
                        'OPERATOR_NOTIFIED',
                        source='api',
                        status='success',
                        message="Operator/group notified of reservation request",
                        metadata={'whatsapp_reservation_id': str(reservation.id)},
                    )
            except Exception as e:
                logger.warning("FlowLogger OPERATOR_NOTIFIED: %s", e)

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
        """Build frontend URL for payment (experience or accommodation checkout with code)."""
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:8080").rstrip("/")
        code = reservation.tour_code
        if reservation.accommodation:
            return f"{frontend_url}/checkout/accommodations/whatsapp?codigo={code}"
        exp = reservation.experience
        if not exp:
            return f"{frontend_url}/checkout/experiences"
        return f"{frontend_url}/checkout/experiences/{exp.slug}?codigo={code}"

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
            # Use existing flow from WhatsApp request if present (started at create_reservation)
            flow = FlowLogger.from_flow_id(reservation.flow_id) if reservation.flow_id else None
            if not flow or not flow.flow:
                try:
                    flow = FlowLogger.start_flow(
                        'experience_booking',
                        experience=experience,
                        organizer=getattr(experience, 'organizer', None),
                        user=None,
                        metadata={
                            'source': 'whatsapp',
                            'whatsapp_reservation_id': str(reservation.id),
                        },
                    )
                    if flow and flow.flow:
                        reservation.flow = flow.flow
                        reservation.save(update_fields=['flow'])
                except Exception as e:
                    logger.warning("FlowLogger experience_booking (legacy): %s", e)
                    flow = None

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
                flow=flow.flow if flow and flow.flow else None,
            )
            reservation.linked_experience_reservation = experience_reservation
            reservation.save(update_fields=['linked_experience_reservation'])
            logger.info(f"Created ExperienceReservation {reservation_id} for WhatsApp reservation {reservation.id}")
            if flow and flow.flow:
                try:
                    flow.log_event(
                        'RESERVATION_CREATED',
                        source='api',
                        status='success',
                        message=f"Experience reservation {reservation_id} created via WhatsApp",
                        metadata={'reservation_id': reservation_id, 'experience_id': str(experience.id)},
                    )
                except Exception as e:
                    logger.warning("FlowLogger RESERVATION_CREATED: %s", e)
            return experience_reservation

    @staticmethod
    def _create_accommodation_reservation_if_needed(reservation) -> bool:
        """Create AccommodationReservation from checkout_data and link to request. Returns True if created."""
        if reservation.linked_accommodation_reservation_id:
            return False
        code_obj = WhatsAppReservationCode.objects.filter(linked_reservation=reservation).first()
        if not code_obj or not code_obj.checkout_data:
            return False
        acc_res = ReservationHandler._create_and_link_accommodation_reservation(reservation, code_obj)
        return acc_res is not None

    @staticmethod
    def _create_and_link_accommodation_reservation(reservation, code_obj):
        """Create AccommodationReservation from checkout_data and link to WhatsAppReservationRequest."""
        from datetime import date as date_type

        checkout_data = code_obj.checkout_data
        accommodation = reservation.accommodation
        if not accommodation:
            return None

        check_in = checkout_data.get("check_in")
        check_out = checkout_data.get("check_out")
        if isinstance(check_in, str):
            try:
                check_in = date_type.fromisoformat(check_in)
            except (ValueError, TypeError):
                return None
        if isinstance(check_out, str):
            try:
                check_out = date_type.fromisoformat(check_out)
            except (ValueError, TypeError):
                return None
        if not check_in or not check_out:
            return None

        pricing = checkout_data.get("pricing", {}) or {}
        total = float(pricing.get("total", 0) or 0)
        currency = pricing.get("currency", "CLP")
        contact = dict(checkout_data.get("contact") or checkout_data.get("customer") or {})
        name = (contact.get("name") or "").strip()
        if name and not contact.get("first_name"):
            parts = name.split(None, 1)
            contact["first_name"] = parts[0]
            contact["last_name"] = parts[1] if len(parts) > 1 else ""

        with transaction.atomic():
            # Use existing flow from WhatsApp request if present (started at create_reservation)
            flow = FlowLogger.from_flow_id(reservation.flow_id) if reservation.flow_id else None
            if not flow or not flow.flow:
                try:
                    flow = FlowLogger.start_flow(
                        'accommodation_booking',
                        accommodation=accommodation,
                        organizer=getattr(accommodation, 'organizer', None),
                        user=None,
                        metadata={
                            'source': 'whatsapp',
                            'whatsapp_reservation_id': str(reservation.id),
                        },
                    )
                    if flow and flow.flow:
                        reservation.flow = flow.flow
                        reservation.save(update_fields=['flow'])
                except Exception as e:
                    logger.warning("FlowLogger accommodation_booking (legacy): %s", e)
                    flow = None

            reservation_id = f"ACC-{uuid.uuid4().hex[:12].upper()}"
            acc_res = AccommodationReservation.objects.create(
                reservation_id=reservation_id,
                accommodation=accommodation,
                status="pending",
                check_in=check_in,
                check_out=check_out,
                guests=int(checkout_data.get("guests", 1)),
                first_name=contact.get("first_name", ""),
                last_name=contact.get("last_name", ""),
                email=contact.get("email", ""),
                phone=reservation.whatsapp_message.phone or "",
                total=total,
                currency=currency,
                flow=flow.flow if flow and flow.flow else None,
            )
            reservation.linked_accommodation_reservation = acc_res
            reservation.save(update_fields=["linked_accommodation_reservation"])
            logger.info("Created AccommodationReservation %s for WhatsApp reservation %s", reservation_id, reservation.id)
            if flow and flow.flow:
                try:
                    flow.log_event(
                        'RESERVATION_CREATED',
                        source='api',
                        status='success',
                        message=f"Accommodation reservation {reservation_id} created via WhatsApp",
                        metadata={'reservation_id': reservation_id, 'accommodation_id': str(accommodation.id)},
                    )
                except Exception as e:
                    logger.warning("FlowLogger RESERVATION_CREATED: %s", e)
            return acc_res

    @staticmethod
    def confirm_availability(reservation):
        """
        Operator confirmed availability. Send appropriate message to customer.
        - If paid (total > 0): create ExperienceReservation, send availability msg + payment link
        - If free: send message asking customer to reply SI to confirm
        """
        reservation.status = 'availability_confirmed'
        reservation.save()

        # 🚀 ENTERPRISE: Log step in platform flow
        if reservation.flow_id:
            try:
                flow = FlowLogger.from_flow_id(reservation.flow_id)
                if flow:
                    flow.log_event(
                        'AVAILABILITY_CONFIRMED',
                        source='api',
                        status='success',
                        message="Operator confirmed availability",
                        metadata={'whatsapp_reservation_id': str(reservation.id)},
                    )
            except Exception as e:
                logger.warning("FlowLogger AVAILABILITY_CONFIRMED: %s", e)

        code_obj = WhatsAppReservationCode.objects.filter(
            linked_reservation=reservation
        ).first()
        total = ReservationHandler._get_total_from_checkout(reservation)
        customer_phone = WhatsAppWebService.clean_phone_number(
            reservation.whatsapp_message.phone
        )
        service = WhatsAppWebService()

        if total > 0:
            # Paid: create ExperienceReservation or AccommodationReservation (needed for payment link)
            if reservation.accommodation:
                ReservationHandler._create_accommodation_reservation_if_needed(reservation)
            else:
                ReservationHandler._create_experience_reservation_if_needed(reservation)
            # Extend code expiration when sending payment link (customer has 30 min to pay)
            if code_obj:
                code_obj.expires_at = timezone.now() + timedelta(minutes=30)
                code_obj.save(update_fields=['expires_at'])
                logger.info(f"Extended code {code_obj.code} expiry for payment link")
            # Send availability message, then payment link
            msg_avail = GroupNotificationService.format_availability_confirmed_message(reservation)
            service.send_message(customer_phone, msg_avail)
            if reservation.flow_id:
                try:
                    flow = FlowLogger.from_flow_id(reservation.flow_id)
                    if flow:
                        flow.log_event(
                            'CUSTOMER_MESSAGE_AVAILABILITY_SENT',
                            source='api',
                            status='success',
                            message="Message sent to customer: availability confirmed",
                            metadata={'whatsapp_reservation_id': str(reservation.id)},
                        )
                except Exception as e:
                    logger.warning("FlowLogger CUSTOMER_MESSAGE_AVAILABILITY_SENT: %s", e)
            payment_url = ReservationHandler._build_payment_url(reservation)
            reservation.payment_link = payment_url
            reservation.payment_link_sent_at = timezone.now()
            reservation.save()
            # 🚀 ENTERPRISE: Log payment link sent
            if reservation.flow_id:
                try:
                    flow = FlowLogger.from_flow_id(reservation.flow_id)
                    if flow:
                        flow.log_event(
                            'PAYMENT_LINK_SENT',
                            source='api',
                            status='success',
                            message="Payment link sent to customer",
                            metadata={'whatsapp_reservation_id': str(reservation.id), 'payment_url': payment_url},
                        )
                except Exception as e:
                    logger.warning("FlowLogger PAYMENT_LINK_SENT: %s", e)
            msg_payment = GroupNotificationService.format_payment_link_message(
                reservation, payment_url
            )
            service.send_message(customer_phone, msg_payment)
            if reservation.flow_id:
                try:
                    flow = FlowLogger.from_flow_id(reservation.flow_id)
                    if flow:
                        flow.log_event(
                            'CUSTOMER_MESSAGE_PAYMENT_LINK_SENT',
                            source='api',
                            status='success',
                            message="Message sent to customer: payment link",
                            metadata={'whatsapp_reservation_id': str(reservation.id)},
                        )
                except Exception as e:
                    logger.warning("FlowLogger CUSTOMER_MESSAGE_PAYMENT_LINK_SENT: %s", e)
            logger.info(f"Sent availability + payment link for reservation {reservation.id}")
        else:
            # Free: ask customer to reply SI to confirm
            msg = GroupNotificationService.format_confirm_free_message(reservation)
            service.send_message(customer_phone, msg)
            if reservation.flow_id:
                try:
                    flow = FlowLogger.from_flow_id(reservation.flow_id)
                    if flow:
                        flow.log_event(
                            'CUSTOMER_MESSAGE_CONFIRM_FREE_SENT',
                            source='api',
                            status='success',
                            message="Message sent to customer: confirm free (responde SI)",
                            metadata={'whatsapp_reservation_id': str(reservation.id)},
                        )
                except Exception as e:
                    logger.warning("FlowLogger CUSTOMER_MESSAGE_CONFIRM_FREE_SENT: %s", e)
            logger.info(f"Sent confirm-free message for reservation {reservation.id}")

    @staticmethod
    def confirm_reservation(reservation):
        """Confirm a free reservation: create ExperienceReservation and notify customer."""
        with transaction.atomic():
            reservation.status = 'confirmed'
            reservation.save()
            GroupNotificationService.send_customer_confirmation(reservation)
            if reservation.flow_id:
                try:
                    flow = FlowLogger.from_flow_id(reservation.flow_id)
                    if flow:
                        flow.log_event(
                            'CUSTOMER_MESSAGE_CONFIRMATION_SENT',
                            source='api',
                            status='success',
                            message="Message sent to customer: reservation confirmed",
                            metadata={'whatsapp_reservation_id': str(reservation.id)},
                        )
                except Exception as e:
                    logger.warning("FlowLogger CUSTOMER_MESSAGE_CONFIRMATION_SENT: %s", e)
            code_obj = WhatsAppReservationCode.objects.filter(linked_reservation=reservation).first()
            if code_obj:
                return ReservationHandler._create_and_link_experience_reservation(reservation, code_obj)
        return None
    
    @staticmethod
    def reject_reservation(reservation):
        """Reject a reservation."""
        reservation.status = 'rejected'
        reservation.save()
        
        # Notify customer (mensaje de rechazo al comprador)
        GroupNotificationService.send_customer_rejection(reservation)
        if reservation.flow_id:
            try:
                flow = FlowLogger.from_flow_id(reservation.flow_id)
                if flow:
                    flow.log_event(
                        'CUSTOMER_MESSAGE_REJECTION_SENT',
                        source='api',
                        status='success',
                        message="Message sent to customer: rejection",
                        metadata={'whatsapp_reservation_id': str(reservation.id)},
                    )
            except Exception as e:
                logger.warning("FlowLogger CUSTOMER_MESSAGE_REJECTION_SENT: %s", e)

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

