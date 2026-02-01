"""Utilities for finding and normalizing Excel headers."""

import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


def normalize_header(header: str) -> str:
    """Normalize header string for comparison."""
    if not header:
        return ''
    # Remove dots, normalize spaces, remove accents, and convert to lowercase
    import unicodedata
    
    normalized = header.strip().lower()
    # Remove accents (é -> e, á -> a, etc.)
    normalized = ''.join(
        c for c in unicodedata.normalize('NFD', normalized)
        if unicodedata.category(c) != 'Mn'
    )
    # Remove dots and normalize spaces
    normalized = normalized.replace('.', '')
    normalized = normalized.replace('  ', ' ')  # Replace double spaces
    normalized = normalized.replace('_', ' ')  # Replace underscores
    normalized = ' '.join(normalized.split())  # Normalize all whitespace
    return normalized


def find_header_row(worksheet, start_row: int = 1, max_rows: int = 20) -> Optional[int]:
    """
    Find the row containing headers.
    
    Looks for common header keywords in the first max_rows rows.
    More robust: checks for multiple header patterns and validates.
    """
    # Extended list of header keywords (more variations)
    # Note: These should match what normalize_header produces (no accents, no dots)
    header_keywords = [
        'salida', 'hora salida', 'hora de salida',
        'destino', 'destinos',
        'operador', 'operadores', 'empresa',
        'placa', 'placas', 'patente',
        'anden', 'andenes',  # Without accents (normalize_header removes them)
        'hora llegada', 'llegada',  # Without dots (normalize_header removes them)
        'origen', 'origenes',
        'observaciones', 'observacion', 'notas'
    ]
    
    best_match = None
    best_score = 0
    
    logger.info(f"🔍 [find_header_row] Searching for header row in rows {start_row} to {min(start_row + max_rows, worksheet.max_row + 1)}")
    logger.info(f"🔍 [find_header_row] Looking for keywords: {header_keywords[:5]}...")
    
    for row_idx in range(start_row, min(start_row + max_rows, worksheet.max_row + 1)):
        row = worksheet[row_idx]
        row_values = []
        
        # Extract all non-empty cell values from the row
        for cell in row:
            if cell.value:
                cell_value = str(cell.value).strip()
                if cell_value:  # Only add non-empty values
                    row_values.append(cell_value.lower())
        
        if not row_values:
            continue
        
        logger.debug(f"📋 Row {row_idx} raw values: {row_values[:10]}")
        
        # Count how many header keywords are found in this row
        found_keywords = 0
        matched_keywords = []
        for keyword in header_keywords:
            for val in row_values:
                normalized_val = normalize_header(val)
                if keyword in normalized_val or normalized_val in keyword:
                    found_keywords += 1
                    matched_keywords.append(f"{keyword} (from '{val}')")
                    break  # Count each keyword only once per row
        
        # Score based on found keywords (weighted)
        score = found_keywords
        
        # Bonus if we find critical headers
        critical_headers = ['salida', 'destino', 'operador', 'hora llegada', 'origen']
        critical_found = sum(1 for keyword in critical_headers 
                            if any(keyword in normalize_header(val) for val in row_values))
        if critical_found >= 2:
            score += 2  # Bonus for critical headers
        
        logger.info(f"📊 Row {row_idx}: found {found_keywords} keywords, score: {score}")
        if matched_keywords:
            logger.debug(f"   Matched keywords: {matched_keywords[:5]}")
        logger.debug(f"   Values: {row_values[:10]}")
        
        if score > best_score:
            best_score = score
            best_match = row_idx
            logger.info(f"   ⭐ New best match! Row {row_idx} with score {score}")
    
    # Require at least 3 header keywords to be confident
    if best_match and best_score >= 3:
        logger.info(f"✅ [find_header_row] SUCCESS: Found header row at index {best_match} with score {best_score}")
        return best_match
    
    logger.warning(f"❌ [find_header_row] FAILED: Could not find header row. Best match: row {best_match} with score {best_score} (need >= 3)")
    return None


def find_header_row_alternative(worksheet, start_row: int = 1, max_rows: int = 20) -> Optional[int]:
    """
    Alternative method: Look for row with mostly text values (headers are usually text).
    """
    for row_idx in range(start_row, min(start_row + max_rows, worksheet.max_row + 1)):
        row = worksheet[row_idx]
        text_count = 0
        total_count = 0
        
        for cell in row:
            if cell.value is not None:
                total_count += 1
                # Headers are usually strings, not numbers or dates
                if isinstance(cell.value, str):
                    text_count += 1
        
        # If most values are text and we have at least 3 columns, likely a header row
        if total_count >= 3 and text_count >= total_count * 0.7:
            # Verify it contains header-like words
            row_text = ' '.join([str(cell.value).lower() for cell in row if cell.value])
            header_indicators = ['salida', 'destino', 'operador', 'placa', 'andén', 'llegada']
            if any(indicator in row_text for indicator in header_indicators):
                return row_idx
    
    return None

