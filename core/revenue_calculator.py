"""
🚀 ENTERPRISE REVENUE CALCULATOR
=================================

This module provides backward-compatible wrappers for the new revenue_system.

DEPRECATED: This file is maintained for backward compatibility only.
New code should import from core.revenue_system instead.

Migration path:
  OLD: from core.revenue_calculator import calculate_event_revenue
  NEW: from core.revenue_system import get_event_revenue
"""

import warnings
from core.revenue_system import (
    get_event_revenue,
    get_ticket_tier_revenue,
    get_organizer_revenue,
    calculate_and_store_effective_values,
    validate_revenue_calculation,
    migrate_order_effective_values,
    migrate_all_orders
)


def calculate_event_revenue(event, start_date=None, end_date=None, validate=False):
    """
    DEPRECATED: Use get_event_revenue from core.revenue_system instead.
    
    This function is maintained for backward compatibility.
    """
    warnings.warn(
        "calculate_event_revenue is deprecated. Use get_event_revenue from core.revenue_system",
        DeprecationWarning,
        stacklevel=2
    )
    return get_event_revenue(event, start_date, end_date, validate)


def calculate_ticket_tier_revenue(ticket_tier, start_date=None, end_date=None, validate=False):
    """
    DEPRECATED: Use get_ticket_tier_revenue from core.revenue_system instead.
    
    This function is maintained for backward compatibility.
    """
    warnings.warn(
        "calculate_ticket_tier_revenue is deprecated. Use get_ticket_tier_revenue from core.revenue_system",
        DeprecationWarning,
        stacklevel=2
    )
    return get_ticket_tier_revenue(ticket_tier, start_date, end_date, validate)


# Re-export for convenience
__all__ = [
    'calculate_event_revenue',
    'calculate_ticket_tier_revenue',
    'get_event_revenue',
    'get_ticket_tier_revenue',
    'get_organizer_revenue',
    'calculate_and_store_effective_values',
    'validate_revenue_calculation',
    'migrate_order_effective_values',
    'migrate_all_orders',
]
