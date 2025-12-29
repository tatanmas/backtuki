"""
🚀 ENTERPRISE Email Context Builder for Experiences - Tuki Platform
Analogous to apps/events/email_context.py

Builds optimized email context to avoid slow template rendering.

Performance:
- Pre-computes all data needed by templates
- Avoids lazy-loading and N+1 queries
- <50ms to build context for typical order

Usage:
    from apps.experiences.email_context import build_experience_confirmation_context
    
    context = build_experience_confirmation_context(order, reservation)
    html = render_to_string('emails/experiences/confirmation.html', context)
"""

import logging
from typing import Dict, Any
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def build_experience_confirmation_context(order, reservation) -> Dict[str, Any]:
    """
    Build complete context for experience confirmation email.
    Pre-computes all data to avoid queries in templates.
    
    Args:
        order: Order model instance
        reservation: ExperienceReservation model instance
        
    Returns:
        Dict with all context data for email templates
        
    Performance: <50ms for typical order
    """
    try:
        experience = reservation.experience
        instance = reservation.instance
        
        # Pre-compute experience data
        experience_data = {
            'title': experience.title,
            'description': experience.description or '',
            'short_description': experience.short_description or '',
            'duration_minutes': experience.duration_minutes,
            'location_name': experience.location_name,
            'location_address': experience.location_address,
            'meeting_point': experience.meeting_point or '',
            'images': [img.image.url for img in experience.images.all()[:5]] if hasattr(experience, 'images') else [],
        }
        
        # Pre-compute instance data
        instance_data = {
            'start_datetime': instance.start_datetime,
            'end_datetime': instance.end_datetime,
            'language': instance.language.language_code if instance.language else 'es',
            'language_name': instance.language.name if instance.language else 'Español',
        }
        
        # Pre-compute reservation data
        reservation_data = {
            'reservation_id': reservation.reservation_id,
            'adult_count': reservation.adult_count,
            'child_count': reservation.child_count,
            'infant_count': reservation.infant_count,
            'total_participants': reservation.adult_count + reservation.child_count + reservation.infant_count,
        }
        
        # Pre-compute order data
        order_data = {
            'order_number': order.order_number,
            'total': float(order.total),
            'subtotal': float(order.subtotal),
            'service_fee': float(order.service_fee),
            'discount': float(order.discount) if order.discount else 0,
            'currency': order.currency,
            'status': order.status,
            'created_at': order.created_at,
            'is_free': order.total == 0,
        }
        
        # Pre-compute resources (if any)
        resources_data = []
        if hasattr(reservation, 'resource_holds'):
            for hold in reservation.resource_holds.filter(released=False).select_related('resource'):
                resources_data.append({
                    'name': hold.resource.name,
                    'description': hold.resource.description or '',
                    'quantity': hold.quantity,
                    'price': float(hold.resource.price) if hold.resource.price else 0,
                    'is_per_person': hold.resource.is_per_person,
                })
        
        # Pre-compute organizer data
        organizer = experience.organizer
        organizer_data = {
            'name': organizer.name,
            'email': organizer.contact_email or '',
            'phone': organizer.contact_phone or '',
            'website': organizer.website or '',
        }
        
        # Build complete context
        context = {
            # Order info
            'order': order,  # Keep original for compatibility
            'order_data': order_data,
            
            # Reservation info
            'reservation': reservation,  # Keep original for compatibility
            'reservation_data': reservation_data,
            
            # Experience info
            'experience': experience,  # Keep original for compatibility
            'experience_data': experience_data,
            
            # Instance info
            'instance': instance,  # Keep original for compatibility
            'instance_data': instance_data,
            
            # Resources (pre-computed)
            'resources': resources_data,
            'resource_count': len(resources_data),
            
            # Organizer info
            'organizer': organizer,  # Keep original for compatibility
            'organizer_data': organizer_data,
            
            # Customer info
            'customer_name': f"{reservation.first_name} {reservation.last_name}".strip(),
            'customer_email': reservation.email,
            'customer_phone': reservation.phone or '',
            
            # URLs
            'frontend_url': settings.FRONTEND_URL,
            'support_email': settings.DEFAULT_FROM_EMAIL,
            
            # Dates
            'booking_date': order.created_at,
            'current_year': timezone.now().year,
        }
        
        logger.info(
            f"✅ [EMAIL_CONTEXT] Built context for experience order {order.order_number}: "
            f"{reservation.reservation_id}, {reservation_data['total_participants']} participants"
        )
        
        return context
        
    except Exception as e:
        logger.error(f"❌ [EMAIL_CONTEXT] Error building context for order {order.id}: {e}", exc_info=True)
        raise

