"""Utilities for parsing time values from Excel."""

from datetime import time
from typing import Optional


def parse_time(time_value) -> Optional[time]:
    """Parse time from Excel cell value."""
    if time_value is None:
        return None
    
    # If already a time object
    if isinstance(time_value, time):
        return time_value
    
    # If datetime, extract time
    if hasattr(time_value, 'time'):
        return time_value.time()
    
    # If string, try to parse
    if isinstance(time_value, str):
        time_str = time_value.strip()
        # Try formats: "5:00", "05:00", "17:30"
        try:
            if ':' in time_str:
                parts = time_str.split(':')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                return time(hour, minute)
        except (ValueError, IndexError):
            pass
    
    return None

