"""Services for terminal advertising management."""

import logging
from django.utils import timezone
from django.db.models import Q

from ..models import TerminalAdvertisingSpace, TerminalAdvertisingInteraction

logger = logging.getLogger(__name__)


def track_interaction(
    advertising_space_id: str,
    interaction_type: str,
    user_ip: str = None,
    user_agent: str = None,
    referrer: str = None,
    destination: str = None
) -> TerminalAdvertisingInteraction:
    """
    Track an interaction with an advertising space.
    
    Args:
        advertising_space_id: UUID of the advertising space
        interaction_type: 'view', 'click', or 'impression'
        user_ip: User IP address (optional)
        user_agent: User agent string (optional)
        referrer: Referrer URL (optional)
        destination: Destination context (optional)
    
    Returns:
        TerminalAdvertisingInteraction instance
    """
    try:
        advertising_space = TerminalAdvertisingSpace.objects.get(id=advertising_space_id)
    except TerminalAdvertisingSpace.DoesNotExist:
        logger.error(f"Advertising space not found: {advertising_space_id}")
        raise ValueError(f"Advertising space not found: {advertising_space_id}")
    
    interaction = TerminalAdvertisingInteraction.objects.create(
        advertising_space=advertising_space,
        interaction_type=interaction_type,
        user_ip=user_ip,
        user_agent=user_agent,
        referrer=referrer,
        destination=destination
    )
    
    logger.debug(f"Tracked {interaction_type} for advertising space {advertising_space_id}")
    return interaction


def get_active_spaces(
    space_type: str = None,
    destination_id: str = None,
    route_origin: str = None,
    route_destination: str = None,
    include_expired: bool = False
) -> list:
    """
    Get active advertising spaces with optional filters.
    
    Args:
        space_type: Filter by space type (optional)
        destination_id: Filter by destination ID (optional)
        route_origin: Filter by route origin (optional)
        route_destination: Filter by route destination (optional)
        include_expired: Include spaces that have expired (default: False)
    
    Returns:
        QuerySet of TerminalAdvertisingSpace instances
    """
    now = timezone.now()
    
    # Base queryset: active spaces
    queryset = TerminalAdvertisingSpace.objects.filter(is_active=True)
    
    # Filter by space type
    if space_type:
        queryset = queryset.filter(space_type=space_type)
    
    # Filter by destination
    if destination_id:
        queryset = queryset.filter(destination_id=destination_id)
    
    # Filter by route origin
    if route_origin:
        queryset = queryset.filter(route_origin=route_origin)
    
    # Filter by route destination
    if route_destination:
        queryset = queryset.filter(route_destination=route_destination)
    
    # Filter by date range
    if not include_expired:
        queryset = queryset.filter(
            Q(display_from__isnull=True) | Q(display_from__lte=now),
            Q(display_until__isnull=True) | Q(display_until__gte=now)
        )
    
    # Order by order field
    queryset = queryset.order_by('order', 'created_at')
    
    return queryset


def get_spaces_by_position(position: str) -> list:
    """
    Get all active spaces for a specific position.
    
    Args:
        position: Position identifier (e.g., 'home_featured_1')
    
    Returns:
        QuerySet of TerminalAdvertisingSpace instances
    """
    return get_active_spaces().filter(position=position)

