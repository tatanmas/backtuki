"""Column detection utilities for complimentary ticket parser."""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Expected column names (normalized, case-insensitive)
EXPECTED_COLUMNS = {
    'first_name': ['nombre', 'first_name', 'firstname', 'nombre_invitado', 'invitado'],
    'last_name': ['apellido', 'apellidos', 'last_name', 'lastname', 'surname'],
    'email': ['email', 'correo', 'e-mail', 'mail', 'correo_electronico']
}


def normalize_column_name(name: str) -> str:
    """Normalize column name for matching."""
    if not name:
        return ''
    # Remove extra spaces, convert to lowercase, remove accents
    normalized = name.strip().lower()
    # Simple accent removal
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u'
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def detect_columns(headers: List[str]) -> Dict[str, Optional[int]]:
    """
    Auto-detect column mapping from headers.
    
    Args:
        headers: List of header strings from file
        
    Returns:
        Dict mapping field names to column indices (0-based)
    """
    mapping = {
        'first_name': None,
        'last_name': None,
        'email': None
    }
    
    for idx, header in enumerate(headers):
        if not header:
            continue
            
        normalized = normalize_column_name(str(header))
        
        # Check each expected column type
        for field_name, possible_names in EXPECTED_COLUMNS.items():
            if mapping[field_name] is None:  # Only assign if not already found
                for possible_name in possible_names:
                    if possible_name in normalized or normalized in possible_name:
                        mapping[field_name] = idx
                        logger.debug(f"Detected column '{header}' as {field_name}")
                        break
                if mapping[field_name] is not None:
                    break
    
    return mapping

