"""Service for creating orders for complimentary tickets."""

import logging
import time
from decimal import Decimal
from apps.events.models import Order, OrderItem, TicketTier

logger = logging.getLogger(__name__)


def create_complimentary_order(
    event,
    ticket_tier: TicketTier,
    attendee_data: dict,
    quantity: int,
    organizer_email: str = None
) -> Order:
    """
    Create a complimentary order (status='paid', total=0).
    
    Args:
        event: Event instance
        ticket_tier: TicketTier instance (complimentary tier)
        attendee_data: Dict with first_name, last_name, email
        quantity: Number of tickets
        organizer_email: Organizer email as fallback if attendee has no email
        
    Returns:
        Order instance
    """
    first_name = attendee_data.get('first_name', 'Invitado')
    last_name = attendee_data.get('last_name', '')
    email = attendee_data.get('email', '').strip()
    
    # For orders, we need an email. Use organizer email if no email provided
    # IMPORTANT: For complimentary tickets, if no email is provided, use placeholder
    # that won't trigger email sending. The system should check if email contains
    # @tuki.live placeholder before sending emails.
    order_email = email
    if not order_email:
        if organizer_email:
            order_email = organizer_email
        else:
            # Use placeholder format that indicates no email should be sent
            # Format: cortesia-{event_id_short}-{timestamp}@tuki.live
            order_email = f"cortesia-{str(event.id)[:8]}-{int(time.time())}@tuki.live"
    
    # Create order
    order = Order.objects.create(
        event=event,
        status='paid',
        email=order_email,
        first_name=first_name,
        last_name=last_name,
        subtotal=Decimal('0.00'),
        service_fee=Decimal('0.00'),
        total=Decimal('0.00'),
        currency='CLP',
        payment_method='complimentary',
        subtotal_effective=Decimal('0.00'),
        service_fee_effective=Decimal('0.00')
    )
    
    logger.info(f"Created complimentary order {order.order_number}")
    return order


def create_complimentary_order_item(order: Order, ticket_tier: TicketTier, quantity: int) -> OrderItem:
    """
    Create order item for complimentary tickets.
    
    Args:
        order: Order instance
        ticket_tier: TicketTier instance
        quantity: Number of tickets
        
    Returns:
        OrderItem instance
    """
    order_item = OrderItem.objects.create(
        order=order,
        ticket_tier=ticket_tier,
        quantity=quantity,
        unit_price=Decimal('0.00'),
        unit_service_fee=Decimal('0.00'),
        subtotal=Decimal('0.00'),
        unit_price_effective=Decimal('0.00'),
        unit_service_fee_effective=Decimal('0.00'),
        subtotal_effective=Decimal('0.00')
    )
    
    logger.debug(f"Created order item for {quantity} complimentary tickets")
    return order_item

