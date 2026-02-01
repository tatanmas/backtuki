"""Services for terminal destination management."""

import logging
from django.utils.text import slugify
from django.db import transaction

from ..models import TerminalDestination, TerminalRoute

logger = logging.getLogger(__name__)


def extract_destinations_from_excel(origins: list, destinations: list) -> list:
    """
    Extract unique destination names from Excel data.
    
    Args:
        origins: List of origin city names
        destinations: List of destination city names
    
    Returns:
        List of unique destination names (combined from origins and destinations)
    """
    all_locations = set()
    
    # Add all origins
    for origin in origins:
        if origin and origin.strip():
            all_locations.add(origin.strip())
    
    # Add all destinations
    for dest in destinations:
        if dest and dest.strip():
            all_locations.add(dest.strip())
    
    return sorted(list(all_locations))


@transaction.atomic
def create_or_update_destinations_from_routes() -> dict:
    """
    Create or update TerminalDestination records from existing TerminalRoute records.
    
    This function extracts unique origin and destination names from all routes
    and creates TerminalDestination records for them if they don't exist.
    
    Returns:
        dict with 'created' and 'updated' counts
    """
    # Get all unique origins and destinations from routes
    origins = TerminalRoute.objects.values_list('origin', flat=True).distinct()
    destinations = TerminalRoute.objects.values_list('destination', flat=True).distinct()
    
    # Combine and deduplicate
    all_locations = sorted(set(list(origins) + list(destinations)))
    
    created_count = 0
    updated_count = 0
    
    for location_name in all_locations:
        if not location_name or not location_name.strip():
            continue
        
        location_name = location_name.strip()
        slug = slugify(location_name)
        
        # Check if destination already exists
        destination, created = TerminalDestination.objects.get_or_create(
            slug=slug,
            defaults={
                'name': location_name,
                'created_from_excel': True,
                'is_active': True,
            }
        )
        
        if created:
            created_count += 1
            logger.info(f"Created destination: {location_name}")
        else:
            # Update name if it changed (but keep slug)
            if destination.name != location_name:
                destination.name = location_name
                destination.save(update_fields=['name'])
                updated_count += 1
                logger.info(f"Updated destination: {location_name}")
    
    return {
        'created': created_count,
        'updated': updated_count,
        'total': len(all_locations)
    }


def get_destinations_from_routes() -> dict:
    """
    Get unique origins and destinations from all routes without creating records.
    
    Returns:
        dict with 'origins', 'destinations', and 'all' lists
    """
    origins = TerminalRoute.objects.values_list('origin', flat=True).distinct().order_by('origin')
    destinations = TerminalRoute.objects.values_list('destination', flat=True).distinct().order_by('destination')
    
    # Combine and deduplicate
    all_locations = sorted(set(list(origins) + list(destinations)))
    
    return {
        'origins': list(origins),
        'destinations': list(destinations),
        'all': all_locations,
    }

