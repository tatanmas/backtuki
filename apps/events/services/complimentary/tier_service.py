"""Service for managing complimentary ticket tiers."""

import logging
from decimal import Decimal
from apps.events.models import Event, TicketTier

logger = logging.getLogger(__name__)


def get_or_create_complimentary_tier(event: Event) -> TicketTier:
    """
    Get or create the complimentary ticket tier for an event.
    
    Args:
        event: Event instance
        
    Returns:
        TicketTier instance for complimentary tickets
    """
    # Check if tier already exists
    tier = TicketTier.objects.filter(
        event=event,
        is_complimentary=True
    ).first()
    
    if tier:
        return tier
    
    # Create new complimentary tier
    tier = TicketTier.objects.create(
        event=event,
        name="Cortesía",
        type="complimentary",
        description="Entrada cortesía",
        price=Decimal('0.00'),
        currency='CLP',
        capacity=None,  # Unlimited
        available=None,  # Unlimited
        is_public=False,  # Not shown in public ticket list
        is_complimentary=True,
        complimentary_tier_for_event=event,
        max_per_order=2,
        min_per_order=1
    )
    
    logger.info(f"Created complimentary tier for event {event.id}")
    return tier

