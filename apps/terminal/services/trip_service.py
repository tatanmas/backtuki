"""Service for managing terminal trips."""

import logging
from typing import Dict, Optional
from django.db import transaction
from django.utils import timezone

from apps.terminal.models import TerminalTrip, TerminalCompany, TerminalRoute

logger = logging.getLogger(__name__)


def create_or_update_trip(trip_data: Dict) -> TerminalTrip:
    """
    Create or update a terminal trip.
    
    Looks for existing trip by: company, route, date, trip_type, departure_time/arrival_time.
    If exists, updates it; otherwise creates new one.
    
    Args:
        trip_data: Dictionary with trip data:
            - company: TerminalCompany instance
            - route: TerminalRoute instance
            - trip_type: 'departure' or 'arrival'
            - date: date object
            - departure_time: time object (for departures) or None
            - arrival_time: time object (for arrivals) or None
            - platform: str or None
            - license_plate: str or None
            - observations: str or None
            - price: Decimal or None
            - currency: str (default 'CLP')
    
    Returns:
        TerminalTrip instance (created or updated)
    """
    company = trip_data['company']
    route = trip_data['route']
    trip_type = trip_data['trip_type']
    trip_date = trip_data['date']
    departure_time = trip_data.get('departure_time')
    arrival_time = trip_data.get('arrival_time')
    
    # Build lookup query
    lookup = {
        'company': company,
        'route': route,
        'date': trip_date,
        'trip_type': trip_type,
    }
    
    # Add time to lookup based on trip_type
    if trip_type == 'departure':
        lookup['departure_time'] = departure_time
        lookup['arrival_time'] = None
    else:  # arrival
        lookup['arrival_time'] = arrival_time
        lookup['departure_time'] = None
    
    # Try to find existing trip
    existing_trip = TerminalTrip.objects.filter(**lookup).first()
    
    if existing_trip:
        # Update existing trip
        if trip_data.get('platform'):
            existing_trip.platform = trip_data['platform']
        if trip_data.get('license_plate'):
            existing_trip.license_plate = trip_data['license_plate']
        if trip_data.get('observations'):
            existing_trip.observations = trip_data['observations']
        
        # Update price if provided
        if 'price' in trip_data:
            existing_trip.price = trip_data.get('price')
        if 'currency' in trip_data:
            existing_trip.currency = trip_data.get('currency', 'CLP')
        
        # Keep seats as NULL (v1)
        existing_trip.total_seats = None
        existing_trip.available_seats = None
        
        # Reset status to available if it was sold_out (new upload = new availability)
        if existing_trip.status == 'sold_out':
            existing_trip.status = 'available'
            existing_trip.is_active = True
        
        existing_trip.save()
        logger.debug(f"Updated trip: {existing_trip}")
        return existing_trip
    
    # Create new trip
    new_trip = TerminalTrip.objects.create(
        company=company,
        route=route,
        trip_type=trip_type,
        date=trip_date,
        departure_time=departure_time,
        arrival_time=arrival_time,
        platform=trip_data.get('platform'),
        license_plate=trip_data.get('license_plate'),
        observations=trip_data.get('observations'),
        total_seats=None,  # v1: not used
        available_seats=None,  # v1: not used
        status='available',
        price=trip_data.get('price'),
        currency=trip_data.get('currency', 'CLP'),
        is_active=True
    )
    
    logger.debug(f"Created new trip: {new_trip}")
    return new_trip

