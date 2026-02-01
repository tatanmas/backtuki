"""
🚀 ENTERPRISE Email Sender for Student Interest Registration - Tuki Platform

Sends confirmation email when a student registers interest in a timeline item.
"""

import logging
from typing import Dict, Any, Optional
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_student_interest_confirmation_email(
    interest_id: str,
    to_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    🚀 ENTERPRISE: Send confirmation email for student interest registration.
    
    Args:
        interest_id: UUID of the StudentInterest instance
        to_email: Optional override email address
        
    Returns:
        Dict with status and details
    """
    try:
        from apps.experiences.models import StudentInterest, StudentCenterTimelineItem
        
        # Get interest with related data
        interest = StudentInterest.objects.select_related(
            'timeline_item',
            'timeline_item__experience',
            'timeline_item__student_center'
        ).prefetch_related(
            'timeline_item__experience__images'
        ).get(id=interest_id)
        
        timeline_item = interest.timeline_item
        experience = timeline_item.experience
        organizer = timeline_item.student_center
        
        # Use provided email or interest email
        recipient_email = to_email or interest.email
        
        logger.info(f"📧 [STUDENT_INTEREST_EMAIL] Sending confirmation to {recipient_email} for experience {experience.title}")
        
        # Build email context
        context = {
            # Student info
            'student_name': interest.name,
            'student_email': interest.email,
            
            # Experience info
            'experience_title': experience.title,
            'experience_description': experience.description or experience.short_description or '',
            'experience_image': None,
            
            # Timeline item info
            'scheduled_date': timeline_item.scheduled_date,
            'scheduled_time': timeline_item.scheduled_date.strftime('%H:%M') if timeline_item.scheduled_date else None,
            'duration_minutes': timeline_item.duration_minutes or experience.duration_minutes,
            'min_participants': timeline_item.min_participants or timeline_item.interest_threshold or 10,
            'max_participants': timeline_item.max_participants or experience.max_participants,
            'location_name': experience.location_name or '',
            
            # Organizer info
            'organizer_name': organizer.name,
            'organizer_email': organizer.contact_email or settings.DEFAULT_FROM_EMAIL,
            
            # Additional context
            'frontend_url': settings.FRONTEND_URL,
            'site_name': 'Tuki',
        }
        
        # Get experience image if available
        if experience.images.exists():
            first_image = experience.images.first()
            if first_image and hasattr(first_image, 'image'):
                try:
                    request = None  # We'll use absolute URL
                    if hasattr(first_image.image, 'url'):
                        # Build absolute URL
                        from django.contrib.sites.models import Site
                        current_site = Site.objects.get_current()
                        protocol = 'https' if settings.USE_HTTPS else 'http'
                        context['experience_image'] = f"{protocol}://{current_site.domain}{first_image.image.url}"
                except Exception as e:
                    logger.warning(f"📧 [STUDENT_INTEREST_EMAIL] Could not get image URL: {e}")
        
        # Format scheduled date for display
        if context['scheduled_date']:
            context['scheduled_date'] = timeline_item.scheduled_date
        
        # Render email templates
        html_message = render_to_string('emails/student_interest_confirmation.html', context)
        text_message = render_to_string('emails/student_interest_confirmation.txt', context)
        
        # Create email
        subject = f'✅ Confirmación de interés: {experience.title}'
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email]
        )
        
        # Attach HTML version
        email.attach_alternative(html_message, "text/html")
        
        # Send email
        email.send()
        
        logger.info(f"✅ [STUDENT_INTEREST_EMAIL] Email sent successfully to {recipient_email}")
        
        return {
            'status': 'success',
            'sent_to': recipient_email,
            'interest_id': str(interest_id),
        }
        
    except Exception as e:
        logger.error(f"❌ [STUDENT_INTEREST_EMAIL] Error sending email: {e}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e),
            'interest_id': str(interest_id),
        }

