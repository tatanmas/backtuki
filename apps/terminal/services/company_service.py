"""Service for managing terminal companies."""

import logging
from typing import Optional
from django.db.models import Q

from apps.terminal.models import TerminalCompany

logger = logging.getLogger(__name__)


def get_or_create_company(operator_name: str) -> TerminalCompany:
    """
    Get or create a terminal company by operator name.
    
    Uses case-insensitive exact matching. If company doesn't exist,
    creates a new one with default values.
    
    Args:
        operator_name: Name of the operator/company from Excel
    
    Returns:
        TerminalCompany instance
    """
    if not operator_name or not operator_name.strip():
        raise ValueError("Operator name cannot be empty")
    
    operator_name = operator_name.strip()
    
    # Case-insensitive exact match
    company = TerminalCompany.objects.filter(
        Q(name__iexact=operator_name)
    ).first()
    
    if company:
        logger.debug(f"Found existing company: {company.name}")
        return company
    
    # Create new company
    company = TerminalCompany.objects.create(
        name=operator_name,
        contact_method='external',
        booking_method='external',
        is_active=True
    )
    
    logger.info(f"Created new company: {company.name} (ID: {company.id})")
    return company

