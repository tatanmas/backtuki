"""Map Excel rows to trip data dictionaries."""

import logging
from datetime import date
from typing import Dict, List, Optional

from .header_mapping import get_expected_headers, TERMINAL_NAME
from .time_parser import parse_time
from .text_formatter import format_title_case

logger = logging.getLogger(__name__)


def map_excel_row_to_trip_data(
    row: List,
    headers: Dict[str, int],
    sheet_date: date,
    upload_type: str
) -> Optional[Dict]:
    """
    Map Excel row data to trip data dictionary.
    
    Args:
        row: List of cell values from Excel row
        headers: Dictionary mapping normalized header names to column indices
        sheet_date: Date parsed from sheet name
        upload_type: 'departures' or 'arrivals'
    
    Returns:
        Dictionary with trip data or None if row is invalid
    """
    # Skip empty rows
    if not any(cell for cell in row):
        return None
    
    expected_headers = get_expected_headers(upload_type)
    
    trip_data = {
        'date': sheet_date,
        'trip_type': upload_type.rstrip('s'),  # 'departures' -> 'departure'
    }
    
    # Extract time
    if upload_type == 'departures':
        salida_col = headers.get('salida')
        if salida_col is not None and salida_col < len(row):
            departure_time = parse_time(row[salida_col])
            if not departure_time:
                logger.warning(f"Could not parse departure time from row: {row}")
                return None
            trip_data['departure_time'] = departure_time
            trip_data['arrival_time'] = None
    else:  # arrivals
        llegada_col = headers.get('hora llegada') or headers.get('hora llegada.')
        if llegada_col is not None and llegada_col < len(row):
            arrival_time = parse_time(row[llegada_col])
            if not arrival_time:
                logger.warning(f"Could not parse arrival time from row: {row}")
                return None
            trip_data['arrival_time'] = arrival_time
            trip_data['departure_time'] = None
    
    # Extract destination/origin
    destino_col = headers.get('destino') or headers.get('origen')
    if destino_col is not None and destino_col < len(row):
        destination = str(row[destino_col]).strip() if row[destino_col] else None
        if not destination:
            logger.warning(f"Missing destination/origin in row: {row}")
            return None
        
        # Format destination to Title Case
        destination = format_title_case(destination)
        
        if upload_type == 'departures':
            trip_data['origin'] = TERMINAL_NAME
            trip_data['destination'] = destination
        else:  # arrivals
            trip_data['origin'] = destination
            trip_data['destination'] = TERMINAL_NAME
    else:
        logger.warning(f"Could not find destination/origin column in row: {row}")
        return None
    
    # Extract operator
    operator_col = headers.get('operador')
    if operator_col is not None and operator_col < len(row):
        operator = str(row[operator_col]).strip() if row[operator_col] else None
        if not operator:
            logger.warning(f"Missing operator in row: {row}")
            return None
        # Format operator to Title Case
        trip_data['operator'] = format_title_case(operator)
    else:
        logger.warning(f"Could not find operator column in row: {row}")
        return None
    
    # Extract optional fields
    platform_col = headers.get('andén') or headers.get('andén.') or headers.get('anden')
    if platform_col is not None and platform_col < len(row):
        platform = str(row[platform_col]).strip() if row[platform_col] else None
        trip_data['platform'] = platform if platform else None
    
    placa_col = headers.get('placa')
    if placa_col is not None and placa_col < len(row):
        license_plate = str(row[placa_col]).strip() if row[placa_col] else None
        trip_data['license_plate'] = license_plate if license_plate else None
    
    observaciones_col = headers.get('observaciones')
    if observaciones_col is not None and observaciones_col < len(row):
        observations = str(row[observaciones_col]).strip() if row[observaciones_col] else None
        trip_data['observations'] = observations if observations else None
    
    return trip_data

