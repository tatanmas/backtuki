"""
Enterprise booking views for experiences (reserve + book flow).
Implements atomic holds, pricing calculation, and overbooking prevention.
"""

import logging
import uuid
from decimal import Decimal
from datetime import timedelta

from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.experiences.models import (
    Experience, TourInstance, ExperienceReservation,
    ExperienceResource, ExperienceCapacityHold, ExperienceResourceHold,
    ExperienceDatePriceOverride
)
from apps.events.models import Order
from apps.creators.models import CreatorProfile
from core.flow_logger import FlowLogger

User = get_user_model()
logger = logging.getLogger(__name__)

# Constants
RESERVATION_EXPIRY_MINUTES = 15

# TUKI Creators: default platform fee and creator commission when not set per experience/organizer
DEFAULT_PLATFORM_FEE_RATE = Decimal('0.15')  # 15%
DEFAULT_CREATOR_COMMISSION_RATE = Decimal('0.5')  # 50% of platform fee


def get_effective_platform_fee_rate(experience):
    """Platform fee rate for experiences: experience → organizer → default."""
    if experience.platform_service_fee_rate is not None:
        return experience.platform_service_fee_rate
    organizer = getattr(experience, 'organizer', None)
    if organizer and getattr(organizer, 'experience_service_fee_rate', None) is not None:
        return organizer.experience_service_fee_rate
    return DEFAULT_PLATFORM_FEE_RATE


def get_effective_creator_commission_rate(experience):
    """Creator share of platform fee: experience override or default 50%."""
    if experience.creator_commission_rate is not None:
        return experience.creator_commission_rate
    return DEFAULT_CREATOR_COMMISSION_RATE


def calculate_pricing(experience, instance, adult_count, child_count, infant_count, selected_resources):
    """
    Calculate pricing with hierarchical precedence: date override > instance override > base.
    Returns dict with subtotal, breakdown, etc.
    """
    # Get base prices from experience
    adult_price = experience.price
    child_price = experience.child_price if experience.is_child_priced else Decimal('0')
    infant_price = experience.infant_price if experience.is_infant_priced else Decimal('0')
    
    # Check for instance overrides
    if instance.override_adult_price is not None:
        adult_price = instance.override_adult_price
    if instance.override_child_price is not None and experience.is_child_priced:
        child_price = instance.override_child_price
    if instance.override_infant_price is not None and experience.is_infant_priced:
        infant_price = instance.override_infant_price
    
    # Check for date overrides (highest precedence)
    date_overrides = ExperienceDatePriceOverride.objects.filter(
        experience=experience,
        date=instance.start_datetime.date()
    )
    
    # Filter by time range if specified
    instance_time = instance.start_datetime.time()
    for override in date_overrides:
        if override.start_time and override.end_time:
            if override.start_time <= instance_time <= override.end_time:
                if override.override_adult_price is not None:
                    adult_price = override.override_adult_price
                if override.override_child_price is not None and experience.is_child_priced:
                    child_price = override.override_child_price
                if override.override_infant_price is not None and experience.is_infant_priced:
                    infant_price = override.override_infant_price
                break
        elif not override.start_time and not override.end_time:
            # Applies to whole day
            if override.override_adult_price is not None:
                adult_price = override.override_adult_price
            if override.override_child_price is not None and experience.is_child_priced:
                child_price = override.override_child_price
            if override.override_infant_price is not None and experience.is_infant_priced:
                infant_price = override.override_infant_price
            break
    
    # Calculate participant subtotal
    participants_subtotal = (
        adult_price * adult_count +
        child_price * child_count +
        infant_price * infant_count
    )
    
    # Calculate resources subtotal
    resources_subtotal = Decimal('0')
    resources_breakdown = []
    
    for res_data in selected_resources:
        try:
            resource = ExperienceResource.objects.get(
                id=res_data['resource_id'],
                experience=experience,
                is_active=True
            )
            quantity = res_data['quantity']
            
            if resource.is_per_person:
                # Price multiplied by total participants
                total_participants = adult_count + child_count + infant_count
                res_total = resource.price * quantity * total_participants
            else:
                # Fixed price per unit
                res_total = resource.price * quantity
            
            resources_subtotal += res_total
            resources_breakdown.append({
                'resource_id': str(resource.id),
                'resource_name': resource.name,
                'quantity': quantity,
                'unit_price': float(resource.price),
                'is_per_person': resource.is_per_person,
                'total': float(res_total)
            })
        except ExperienceResource.DoesNotExist:
            logger.warning(f"Resource {res_data['resource_id']} not found")
            continue
    
    subtotal = participants_subtotal + resources_subtotal
    
    # Platform service fee (TUKI Creators: configurable per experience / organizer)
    rate = get_effective_platform_fee_rate(experience)
    service_fee = (subtotal * rate).quantize(Decimal('1'))
    
    # Discount (from coupons, etc.)
    discount = Decimal('0')  # TODO: implement discount logic
    
    total = subtotal + service_fee - discount
    
    return {
        'subtotal': subtotal,
        'service_fee': service_fee,
        'discount': discount,
        'total': total,
        'currency': experience.currency,
        'breakdown': {
            'adult_price': float(adult_price),
            'child_price': float(child_price),
            'infant_price': float(infant_price),
            'adult_count': adult_count,
            'child_count': child_count,
            'infant_count': infant_count,
            'participants_subtotal': float(participants_subtotal),
            'resources': resources_breakdown,
            'resources_subtotal': float(resources_subtotal),
        }
    }


def calculate_capacity_units(adult_count, child_count, infant_count, rule):
    """Calculate capacity units based on counting rule."""
    if rule == 'all':
        return adult_count + child_count + infant_count
    elif rule == 'exclude_infants':
        return adult_count + child_count
    elif rule == 'adults_only':
        return adult_count
    return adult_count + child_count + infant_count  # default


def cleanup_expired_holds(instance):
    """Release expired holds for an instance."""
    now = timezone.now()
    
    # Release expired capacity holds
    ExperienceCapacityHold.objects.filter(
        instance=instance,
        released=False,
        expires_at__lt=now
    ).update(released=True, released_at=now)
    
    # Release expired resource holds
    ExperienceResourceHold.objects.filter(
        instance=instance,
        released=False,
        expires_at__lt=now
    ).update(released=True, released_at=now)


def check_capacity_available(instance, capacity_units_needed, exclude_reservation_id=None):
    """
    Check if capacity is available (atomic check).
    Returns (available: bool, current_held: int, max_capacity: int)
    """
    max_capacity = instance.max_capacity
    if max_capacity is None:
        max_capacity = instance.experience.max_participants
    
    if max_capacity is None:
        return True, 0, None  # Unlimited
    
    # Sum active holds (not released, not expired)
    now = timezone.now()
    active_holds = ExperienceCapacityHold.objects.filter(
        instance=instance,
        released=False,
        expires_at__gte=now
    )
    
    if exclude_reservation_id:
        active_holds = active_holds.exclude(reservation__reservation_id=exclude_reservation_id)
    
    current_held = active_holds.aggregate(total=Sum('capacity_units'))['total'] or 0
    
    available_capacity = max_capacity - current_held
    
    return available_capacity >= capacity_units_needed, current_held, max_capacity


def check_resources_available(instance, selected_resources, exclude_reservation_id=None):
    """
    Check if all requested resources are available.
    Returns (available: bool, errors: list)
    """
    now = timezone.now()
    errors = []
    
    for res_data in selected_resources:
        try:
            resource = ExperienceResource.objects.get(id=res_data['resource_id'], is_active=True)
            
            if resource.available_quantity is None:
                continue  # Unlimited
            
            requested_qty = res_data['quantity']
            
            # Sum active holds for this resource on this instance
            active_holds = ExperienceResourceHold.objects.filter(
                resource=resource,
                instance=instance,
                released=False,
                expires_at__gte=now
            )
            
            if exclude_reservation_id:
                active_holds = active_holds.exclude(reservation__reservation_id=exclude_reservation_id)
            
            current_held = active_holds.aggregate(total=Sum('quantity'))['total'] or 0
            available = resource.available_quantity - current_held
            
            if available < requested_qty:
                errors.append(f"Resource '{resource.name}' only has {available} units available (requested {requested_qty})")
        
        except ExperienceResource.DoesNotExist:
            errors.append(f"Resource {res_data['resource_id']} not found")
    
    return len(errors) == 0, errors


class PublicExperienceReserveView(APIView):
    """
    Public endpoint to reserve capacity (create/update pending reservation with holds).
    POST /api/v1/experiences/public/<experience_id>/reserve
    """
    
    permission_classes = [permissions.AllowAny]
    
    @transaction.atomic
    def post(self, request, experience_id):
        """Create or update a reservation with holds."""
        try:
            experience = Experience.objects.select_for_update().get(
                id=experience_id,
                status='published'
            )
        except Experience.DoesNotExist:
            return Response(
                {'error': 'Experience not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Parse request
        instance_id = request.data.get('instance_id')
        adult_count = request.data.get('adult_count', 1)
        child_count = request.data.get('child_count', 0)
        infant_count = request.data.get('infant_count', 0)
        selected_resources = request.data.get('selected_resources', [])  # [{resource_id, quantity}]
        reservation_id = request.data.get('reservation_id')  # For updating existing reservation
        creator_slug = request.data.get('creator_slug') or request.data.get('ref')  # TUKI Creators attribution
        
        # Contact info (optional at reserve stage, required at book)
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        email = request.data.get('email', '')
        phone = request.data.get('phone', '')
        
        # Validate
        if not instance_id:
            return Response({'error': 'instance_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            instance = TourInstance.objects.select_for_update().get(
                id=instance_id,
                experience=experience,
                status='active'
            )
        except TourInstance.DoesNotExist:
            return Response({'error': 'Instance not found or not available'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check sales cutoff
        cutoff_time = instance.start_datetime - timedelta(hours=experience.sales_cutoff_hours)
        if timezone.now() > cutoff_time:
            return Response(
                {'error': f'Booking closed. Sales cutoff is {experience.sales_cutoff_hours} hours before start.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Cleanup expired holds
        cleanup_expired_holds(instance)
        
        # Calculate capacity needed
        capacity_units = calculate_capacity_units(
            adult_count, child_count, infant_count,
            experience.capacity_count_rule
        )
        
        # Check capacity
        capacity_available, current_held, max_cap = check_capacity_available(
            instance, capacity_units, exclude_reservation_id=reservation_id
        )
        
        if not capacity_available:
            return Response(
                {
                    'error': 'Not enough capacity available',
                    'details': {
                        'requested': capacity_units,
                        'available': max_cap - current_held if max_cap else 'unlimited',
                        'max_capacity': max_cap
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check resources
        resources_available, resource_errors = check_resources_available(
            instance, selected_resources, exclude_reservation_id=reservation_id
        )
        
        if not resources_available:
            return Response(
                {'error': 'Resources not available', 'details': resource_errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate pricing
        pricing = calculate_pricing(
            experience, instance, adult_count, child_count, infant_count, selected_resources
        )
        
        # Create or update reservation
        expires_at = timezone.now() + timedelta(minutes=RESERVATION_EXPIRY_MINUTES)
        
        if reservation_id:
            # Update existing reservation
            try:
                reservation = ExperienceReservation.objects.select_for_update().get(
                    reservation_id=reservation_id,
                    status='pending'
                )
                
                # Release old holds
                reservation.capacity_holds.filter(released=False).update(released=True, released_at=timezone.now())
                reservation.resource_holds.filter(released=False).update(released=True, released_at=timezone.now())
                
                # Update reservation
                reservation.instance = instance
                reservation.adult_count = adult_count
                reservation.child_count = child_count
                reservation.infant_count = infant_count
                reservation.first_name = first_name or reservation.first_name
                reservation.last_name = last_name or reservation.last_name
                reservation.email = email or reservation.email
                reservation.phone = phone or reservation.phone
                reservation.subtotal = pricing['subtotal']
                reservation.service_fee = pricing['service_fee']
                reservation.discount = pricing['discount']
                reservation.total = pricing['total']
                reservation.currency = pricing['currency']
                reservation.pricing_details = pricing['breakdown']
                reservation.selected_resources = selected_resources
                reservation.capacity_count_rule = experience.capacity_count_rule
                reservation.expires_at = expires_at
                reservation.save()
                
            except ExperienceReservation.DoesNotExist:
                return Response({'error': 'Reservation not found or already processed'}, status=status.HTTP_404_NOT_FOUND)
        else:
            # Resolve creator for attribution (TUKI Creators)
            creator = None
            if creator_slug:
                try:
                    creator = CreatorProfile.objects.get(slug=creator_slug, is_approved=True)
                except CreatorProfile.DoesNotExist:
                    pass
            
            # Create new reservation
            reservation_id_str = f"EXP-{uuid.uuid4().hex[:12].upper()}"
            creator_commission_amount = Decimal('0')
            creator_commission_status = None
            if creator:
                creator_rate = get_effective_creator_commission_rate(experience)
                creator_commission_amount = (pricing['service_fee'] * creator_rate).quantize(Decimal('1'))
                creator_commission_status = 'pending'
            
            reservation = ExperienceReservation.objects.create(
                reservation_id=reservation_id_str,
                experience=experience,
                instance=instance,
                status='pending',
                adult_count=adult_count,
                child_count=child_count,
                infant_count=infant_count,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                subtotal=pricing['subtotal'],
                service_fee=pricing['service_fee'],
                discount=pricing['discount'],
                total=pricing['total'],
                currency=pricing['currency'],
                pricing_details=pricing['breakdown'],
                selected_resources=selected_resources,
                capacity_count_rule=experience.capacity_count_rule,
                expires_at=expires_at,
                creator=creator,
                creator_commission_amount=creator_commission_amount,
                creator_commission_status=creator_commission_status,
            )
            
            # 🚀 ENTERPRISE: Start flow tracking for new reservations
            user = request.user if request.user.is_authenticated else None
            flow = FlowLogger.start_flow(
                'experience_booking',
                user=user,
                organizer=experience.organizer,
                experience=experience,
                metadata={
                    'reservation_id': reservation.reservation_id,
                    'instance_id': str(instance.id),
                    'participants': {
                        'adults': adult_count,
                        'children': child_count,
                        'infants': infant_count,
                    },
                    'creator_slug': creator_slug or '',
                }
            )
            
            # TUKI Creators: attach creator to flow for attribution
            if flow and flow.flow and creator:
                flow.flow.creator = creator
                flow.flow.save(update_fields=['creator'])
            
            flow.log_event(
                'RESERVATION_CREATED',
                source='api',
                status='success',
                message=f"Reservation {reservation.reservation_id} created",
                metadata={'expires_at': reservation.expires_at.isoformat()}
            )
            
            # ✅ CRÍTICO: Guardar flow como FK directo (no string)
            reservation.flow = flow.flow
            reservation.save()
        
        # Create capacity hold
        ExperienceCapacityHold.objects.create(
            instance=instance,
            reservation=reservation,
            capacity_units=capacity_units,
            expires_at=expires_at,
            released=False
        )
        
        # Create resource holds
        for res_data in selected_resources:
            try:
                resource = ExperienceResource.objects.get(id=res_data['resource_id'], is_active=True)
                ExperienceResourceHold.objects.create(
                    resource=resource,
                    reservation=reservation,
                    instance=instance,
                    quantity=res_data['quantity'],
                    expires_at=expires_at,
                    released=False
                )
            except ExperienceResource.DoesNotExist:
                pass
        
        return Response({
            'reservation_id': reservation.reservation_id,
            'expires_at': reservation.expires_at.isoformat(),
            'pricing': {
                'subtotal': float(reservation.subtotal),
                'service_fee': float(reservation.service_fee),
                'discount': float(reservation.discount),
                'total': float(reservation.total),
                'currency': reservation.currency,
                'breakdown': reservation.pricing_details
            },
            'participants': {
                'adult_count': reservation.adult_count,
                'child_count': reservation.child_count,
                'infant_count': reservation.infant_count,
            }
        }, status=status.HTTP_200_OK if reservation_id else status.HTTP_201_CREATED)


class PublicExperienceBookView(APIView):
    """
    Public endpoint to confirm a reservation (create Order and finalize booking).
    POST /api/v1/experiences/public/<experience_id>/book
    """
    
    permission_classes = [permissions.AllowAny]
    
    @transaction.atomic
    def post(self, request, experience_id):
        """Confirm reservation and create Order."""
        reservation_id = request.data.get('reservation_id')
        
        if not reservation_id:
            return Response({'error': 'reservation_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            reservation = ExperienceReservation.objects.select_for_update().get(
                reservation_id=reservation_id,
                experience_id=experience_id,
                status='pending'
            )
        except ExperienceReservation.DoesNotExist:
            return Response(
                {'error': 'Reservation not found or already processed'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Allow frontend to send contact info (e.g. from BuyerInfo form in codigo flow)
        contact_info = request.data.get('contact_info') or {}
        if contact_info:
            if contact_info.get('first_name'):
                reservation.first_name = contact_info['first_name'].strip()
            if contact_info.get('last_name') is not None:
                reservation.last_name = (contact_info['last_name'] or '-').strip()
            elif not reservation.last_name:
                reservation.last_name = reservation.first_name or '-'
            if contact_info.get('email'):
                reservation.email = contact_info['email'].strip()
            if contact_info.get('phone') is not None:
                reservation.phone = (contact_info['phone'] or '').strip()
            reservation.save(update_fields=['first_name', 'last_name', 'email', 'phone'])
        
        # Normalize: last_name empty -> use "-" for validation
        if not (reservation.last_name or '').strip():
            reservation.last_name = reservation.first_name or '-'
            reservation.save(update_fields=['last_name'])
        
        # Check expiry
        if reservation.expires_at and timezone.now() > reservation.expires_at:
            reservation.status = 'expired'
            reservation.save()
            # Release holds
            reservation.capacity_holds.filter(released=False).update(released=True, released_at=timezone.now())
            reservation.resource_holds.filter(released=False).update(released=True, released_at=timezone.now())
            return Response({'error': 'Reservation expired'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate contact info (first_name and email required; last_name defaults to "-")
        if not (reservation.first_name or '').strip():
            return Response(
                {'error': 'Nombre requerido. Completa el formulario de contacto.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not (reservation.email or '').strip():
            return Response(
                {'error': 'Email requerido. Completa el formulario de contacto.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get or create user
        user = None
        try:
            user = User.objects.get(email__iexact=reservation.email)
        except User.DoesNotExist:
            user = User.create_guest_user(
                email=reservation.email,
                first_name=reservation.first_name,
                last_name=reservation.last_name
            )
        
        reservation.user = user
        
        # 🚀 ENTERPRISE: Get or continue flow from reservation
        flow = FlowLogger(reservation.flow) if reservation.flow else None
        
        # Create Order
        if reservation.total == 0:
            # Free experience: confirm immediately
            order = Order.objects.create(
                user=user,
                email=reservation.email,
                first_name=reservation.first_name,
                last_name=reservation.last_name,
                phone=reservation.phone or "",
                total=reservation.total,
                subtotal=reservation.subtotal,
                service_fee=reservation.service_fee,
                discount=reservation.discount,
                taxes=Decimal('0'),
                order_kind='experience',
                experience_reservation=reservation,
                status='paid',
                flow=flow.flow if flow else None,  # ✅ CRÍTICO: FK directo
            )
            
            if flow:
                flow.update_order(order)
                flow.log_event(
                    'ORDER_CREATED',
                    order=order,
                    source='api',
                    status='success',
                    message=f"Order {order.order_number} created",
                    metadata={'total': float(order.total), 'is_free': True}
                )
                
                flow.log_event(
                    'ORDER_MARKED_PAID',
                    order=order,
                    source='api',
                    status='success',
                    message=f"Free order {order.order_number} marked as paid"
                )
                
                # ✅ EMAIL_PENDING (NO enviar directamente)
                flow.log_event(
                    'EMAIL_PENDING',
                    order=order,
                    source='api',
                    status='info',
                    message=f"Email pending - will be sent from confirmation page",
                    metadata={
                        'email_strategy': 'frontend_sync',
                        'fallback_to_celery': True,
                        'flow_type': 'free_experience'
                    }
                )
            
            reservation.status = 'paid'
            reservation.paid_at = timezone.now()
            reservation.save()
            
            # ✅ CRÍTICO: Incluir access_token en respuesta (seguridad)
            return Response({
                'status': 'confirmed',
                'reservation_id': reservation.reservation_id,
                'order_id': str(order.id),
                'order_number': order.order_number,
                'accessToken': order.access_token,  # ✅ Para seguridad en endpoint sync
                'message': 'Booking confirmed (free experience)'
            }, status=status.HTTP_200_OK)
        
        else:
            # Paid experience: create pending Order and return order_id for payment
            order = Order.objects.create(
                user=user,
                email=reservation.email,
                first_name=reservation.first_name,
                last_name=reservation.last_name,
                phone=reservation.phone or "",
                total=reservation.total,
                subtotal=reservation.subtotal,
                service_fee=reservation.service_fee,
                discount=reservation.discount,
                taxes=Decimal('0'),
                order_kind='experience',
                experience_reservation=reservation,
                status='pending',
                flow=flow.flow if flow else None,  # ✅ CRÍTICO: FK directo
            )
            
            if flow:
                flow.update_order(order)
                flow.log_event(
                    'ORDER_CREATED',
                    order=order,
                    source='api',
                    status='success',
                    message=f"Order {order.order_number} created",
                    metadata={'total': float(order.total), 'is_free': False}
                )
            
            # ✅ CRÍTICO: Incluir access_token en respuesta
            return Response({
                'status': 'pending_payment',
                'reservation_id': reservation.reservation_id,
                'order_id': str(order.id),
                'order_number': order.order_number,
                'accessToken': order.access_token,  # ✅ Para seguridad en endpoint sync
                'total': float(reservation.total),
                'currency': reservation.currency,
                'message': 'Proceed to payment'
            }, status=status.HTTP_200_OK)

