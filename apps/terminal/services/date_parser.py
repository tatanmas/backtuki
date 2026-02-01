"""Service for parsing dates from Excel sheet names."""

import re
from datetime import date, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Spanish day names mapping
SPANISH_DAYS = {
    'lunes': 0,
    'martes': 1,
    'miercoles': 2,
    'miércoles': 2,
    'jueves': 3,
    'viernes': 4,
    'sabado': 5,
    'sábado': 5,
    'domingo': 6,
}


def parse_sheet_date(
    sheet_name: str,
    date_range_start: date,
    date_range_end: date
) -> Optional[date]:
    """
    Parse date from Excel sheet name.
    
    Expected format: "LUNES 29", "MARTES 30", etc.
    Uses date_range_start and date_range_end to infer year and month.
    
    Args:
        sheet_name: Name of the Excel sheet (e.g., "LUNES 29")
        date_range_start: Start date of the range
        date_range_end: End date of the range
    
    Returns:
        Parsed date or None if parsing fails
    """
    try:
        # Normalize sheet name: remove extra spaces, convert to lowercase
        sheet_name = sheet_name.strip().lower()
        
        # Extract day name and day number
        # Pattern: day_name (optional spaces) day_number
        pattern = r'^([a-záéíóúñ]+)\s+(\d{1,2})'
        match = re.match(pattern, sheet_name)
        
        if not match:
            logger.warning(f"Could not parse sheet name format: {sheet_name}")
            return None
        
        day_name = match.group(1)
        day_number = int(match.group(2))
        
        # Get day of week (0=Monday, 6=Sunday)
        if day_name not in SPANISH_DAYS:
            logger.warning(f"Unknown day name: {day_name}")
            return None
        
        target_weekday = SPANISH_DAYS[day_name]
        
        # Find the date within the range that matches the day number and weekday
        current_date = date_range_start
        while current_date <= date_range_end:
            # Check if day number matches
            if current_date.day == day_number:
                # Check if weekday matches
                if current_date.weekday() == target_weekday:
                    return current_date
            current_date += timedelta(days=1)
        
        logger.warning(
            f"Could not find date matching {day_name} {day_number} "
            f"in range {date_range_start} to {date_range_end}"
        )
        return None
        
    except Exception as e:
        logger.error(f"Error parsing sheet date from '{sheet_name}': {e}", exc_info=True)
        return None

