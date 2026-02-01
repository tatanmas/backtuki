"""Service for creating tickets for complimentary orders."""

import logging
from typing import List
from apps.events.models import Ticket, OrderItem
from apps.events.qr_generator import generate_ticket_qr

logger = logging.getLogger(__name__)


def create_complimentary_tickets(
    order_item: OrderItem,
    attendee_data: dict,
    quantity: int
) -> List[Ticket]:
    """
    Create tickets for a complimentary order item.
    
    Args:
        order_item: OrderItem instance
        attendee_data: Dict with first_name, last_name, email
        quantity: Number of tickets to create
        
    Returns:
        List of created Ticket instances
    """
    tickets = []
    
    first_name = attendee_data.get('first_name', 'Invitado')
    last_name = attendee_data.get('last_name', '')
    email = attendee_data.get('email', '').strip()
    
    for i in range(quantity):
        ticket = Ticket.objects.create(
            order_item=order_item,
            first_name=first_name,
            last_name=last_name,
            email=email,  # Can be empty for complimentary tickets
            status='active'
        )
        
        # Generate QR code
        try:
            generate_ticket_qr(ticket, save=True)
        except Exception as e:
            logger.error(f"Error generating QR for ticket {ticket.ticket_number}: {e}")
        
        tickets.append(ticket)
        logger.debug(f"Created complimentary ticket {ticket.ticket_number}")
    
    return tickets

