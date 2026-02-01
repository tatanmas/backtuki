"""Parse individual Excel sheets."""

import logging
from datetime import date
from typing import Dict, List, Tuple

from apps.terminal.services.date_parser import parse_sheet_date
from .header_finder import find_header_row, normalize_header
from .header_mapping import get_expected_headers
from .row_mapper import map_excel_row_to_trip_data

logger = logging.getLogger(__name__)


def parse_sheet(
    worksheet,
    sheet_name: str,
    upload_type: str,
    date_range_start: date,
    date_range_end: date
) -> Tuple[List[Dict], List[str]]:
    """
    Parse a single Excel sheet.
    
    Returns:
        Tuple of (list of trip data dicts, list of error messages)
    """
    trips = []
    errors = []
    
    # Parse date from sheet name
    sheet_date = parse_sheet_date(sheet_name, date_range_start, date_range_end)
    if not sheet_date:
        errors.append(f"Could not parse date from sheet name: {sheet_name}")
        return trips, errors
    
    # Find header row (try primary method first, then alternative)
    header_row_idx = find_header_row(worksheet)
    if header_row_idx is None:
        from .header_finder import find_header_row_alternative
        header_row_idx = find_header_row_alternative(worksheet)
    
    if header_row_idx is None:
        errors.append(f"Could not find header row in sheet: {sheet_name}")
        return trips, errors
    
    # Extract headers
    header_row = worksheet[header_row_idx]
    headers = {}
    expected_headers = get_expected_headers(upload_type)
    
    for col_idx, cell in enumerate(header_row):
        if cell.value:
            normalized = normalize_header(str(cell.value))
            if normalized in expected_headers:
                headers[normalized] = col_idx
    
    if not headers:
        errors.append(f"Could not find expected headers in sheet: {sheet_name}")
        return trips, errors
    
    # Parse data rows
    data_start_row = header_row_idx + 1
    for row_idx in range(data_start_row, worksheet.max_row + 1):
        row = [cell.value for cell in worksheet[row_idx]]
        
        try:
            trip_data = map_excel_row_to_trip_data(row, headers, sheet_date, upload_type)
            if trip_data:
                trips.append(trip_data)
        except Exception as e:
            error_msg = f"Error parsing row {row_idx} in sheet {sheet_name}: {e}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)
    
    return trips, errors

