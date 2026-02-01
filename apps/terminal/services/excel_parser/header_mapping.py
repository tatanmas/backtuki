"""Header mapping configuration for Excel parsing."""

# Expected column headers (normalized - no accents, no dots, lowercase)
# These keys should match what normalize_header() produces
# normalize_header removes accents, dots, and normalizes spaces
EXPECTED_HEADERS_DEPARTURES = {
    'hora llegada': None,  # Not used for departures (normalized from "HORA LLEGADA." or "HORA LLEGADA")
    'salida': 'departure_time',
    'destino': 'destination',
    'anden': 'platform',  # Normalized from "ANDEN", "ANDÉN", "ANDÉN.", etc.
    'operador': 'operator',
    'placa': 'license_plate',
    'observaciones': 'observations',
}

EXPECTED_HEADERS_ARRIVALS = {
    'hora llegada': 'arrival_time',  # Normalized from "HORA LLEGADA." or "HORA LLEGADA"
    'salida': None,  # Not used for arrivals
    'destino': 'origin',  # For arrivals, "destino" is actually the origin
    'origen': 'origin',
    'anden': 'platform',  # Normalized from "ANDEN", "ANDÉN", "ANDÉN.", etc.
    'operador': 'operator',
    'placa': 'license_plate',
    'observaciones': 'observations',
}

# Terminal name constant
TERMINAL_NAME = 'Coyhaique'


def get_expected_headers(upload_type: str) -> dict:
    """Get expected headers based on upload type."""
    if upload_type == 'departures':
        return EXPECTED_HEADERS_DEPARTURES
    return EXPECTED_HEADERS_ARRIVALS
