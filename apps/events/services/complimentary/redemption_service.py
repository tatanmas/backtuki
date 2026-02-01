"""Main service for redeeming complimentary ticket invitations."""

import logging
from typing import Dict, List
from django.db import transaction

from apps.events.models import ComplimentaryTicketInvitation
from .tier_service import get_or_create_complimentary_tier
from .order_creator import create_complimentary_order, create_complimentary_order_item
from .ticket_creator import create_complimentary_tickets

logger = logging.getLogger(__name__)


@transaction.atomic
def redeem_invitation(
    invitation: ComplimentaryTicketInvitation,
    user_data: Dict[str, str],
    ticket_quantity: int
) -> List:
    """
    Redeem a complimentary ticket invitation.
    
    Args:
        invitation: ComplimentaryTicketInvitation instance
        user_data: Dict with first_name, last_name, email
        ticket_quantity: Number of tickets to generate (1 or 2)
        
    Returns:
        List of created Ticket instances
    """
    # Validate invitation status
    if invitation.status != 'pending':
        raise ValueError(f"Invitation cannot be redeemed (status: {invitation.status})")
    
    # Validate ticket quantity
    if ticket_quantity < 1 or ticket_quantity > invitation.max_tickets:
        raise ValueError(f"Invalid ticket quantity: {ticket_quantity} (max: {invitation.max_tickets})")
    
    # Get or create complimentary tier
    ticket_tier = get_or_create_complimentary_tier(invitation.event)
    
    # Prepare attendee data (use provided data or fallback to invitation data)
    attendee_data = {
        'first_name': user_data.get('first_name', '').strip() or invitation.first_name or 'Invitado',
        'last_name': user_data.get('last_name', '').strip() or invitation.last_name or '',
        'email': user_data.get('email', '').strip() or invitation.email or ''
    }
    
    # Get organizer email for fallback
    # Organizer has contact_email, or we can get from first OrganizerUser
    organizer_email = None
    if invitation.event.organizer:
        organizer = invitation.event.organizer
        # First try contact_email
        if organizer.contact_email:
            organizer_email = organizer.contact_email
        else:
            # Fallback: get from first OrganizerUser
            organizer_user = organizer.organizer_users.first()
            if organizer_user and organizer_user.user:
                organizer_email = organizer_user.user.email
    
    # Create order
    order = create_complimentary_order(
        event=invitation.event,
        ticket_tier=ticket_tier,
        attendee_data=attendee_data,
        quantity=ticket_quantity,
        organizer_email=organizer_email
    )
    
    # Create order item
    order_item = create_complimentary_order_item(order, ticket_tier, ticket_quantity)
    
    # Create tickets
    tickets = create_complimentary_tickets(order_item, attendee_data, ticket_quantity)
    
    # Update invitation
    invitation.status = 'redeemed'
    invitation.redeemed_at = invitation.updated_at
    invitation.redeemed_by_email = attendee_data['email'] if attendee_data['email'] else None
    invitation.order = order
    invitation.save()
    
    logger.info(
        f"Redeemed invitation {invitation.public_token}: "
        f"{ticket_quantity} tickets created (order: {order.order_number})"
    )
    
    return tickets

