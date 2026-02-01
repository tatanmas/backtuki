"""Text file parser for complimentary ticket invitations."""

import logging
from typing import Dict, List, Tuple

from .column_detector import detect_columns

logger = logging.getLogger(__name__)


def parse_text_file(text: str, delimiter: str = '\t') -> Tuple[List[Dict], List[str]]:
    """
    Parse text data (tab-separated or comma-separated).
    
    Args:
        text: Text content
        delimiter: Delimiter character (default: tab)
        
    Returns:
        Tuple of (list of data dicts, list of error messages)
    """
    entries = []
    errors = []
    
    try:
        lines = text.strip().split('\n')
        if not lines:
            errors.append("Text file is empty")
            return entries, errors
        
        # First line is headers
        headers_line = lines[0]
        headers = [h.strip() for h in headers_line.split(delimiter)]
        
        # Auto-detect column mapping
        column_mapping = detect_columns(headers)
        
        # Parse data rows
        entries = _parse_text_rows(lines[1:], column_mapping, delimiter)
        
        logger.info(f"Parsed {len(entries)} entries from text file")
        
    except Exception as e:
        error_msg = f"Error parsing text file: {str(e)}"
        logger.error(error_msg, exc_info=True)
        errors.append(error_msg)
    
    return entries, errors


def _parse_text_rows(lines: List[str], column_mapping: Dict, delimiter: str) -> List[Dict]:
    """Parse data rows from text lines."""
    entries = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        values = [v.strip() for v in line.split(delimiter)]
        entry = _extract_row_data_from_values(values, column_mapping)
        
        # Only add if has at least first_name or email
        if entry.get('first_name') or entry.get('email'):
            entries.append(entry)
    
    return entries


def _extract_row_data_from_values(values: List[str], column_mapping: Dict) -> Dict:
    """Extract data from a row's values based on column mapping."""
    entry = {}
    
    # Extract first_name
    if column_mapping['first_name'] is not None:
        idx = column_mapping['first_name']
        if idx < len(values):
            entry['first_name'] = values[idx]
    
    # Extract last_name
    if column_mapping['last_name'] is not None:
        idx = column_mapping['last_name']
        if idx < len(values):
            entry['last_name'] = values[idx]
    
    # Extract email
    if column_mapping['email'] is not None:
        idx = column_mapping['email']
        if idx < len(values):
            email = values[idx]
            # Handle multiple emails separated by semicolon
            if ';' in email:
                email = email.split(';')[0].strip()
            entry['email'] = email
    
    return entry

