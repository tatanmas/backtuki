"""Parser for extracting information from WhatsApp messages."""
import re
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class MessageParser:
    """Parse WhatsApp messages to extract reservation information."""
    
    # Patterns for tour code extraction
    TOUR_CODE_PATTERNS = [
        r'(?:tour|TOUR|exp|EXP)[-_\s]?([A-Z0-9]{3,12})',  # TOUR-ABC123, EXP-ABC123
        r'código[:\s]+([A-Z0-9]{3,12})',  # código: ABC123
        r'code[:\s]+([A-Z0-9]{3,12})',  # code: ABC123
    ]
    
    # Patterns for passenger count
    PASSENGER_PATTERNS = [
        r'(\d+)\s*(?:personas?|pasajeros?|pax|people)',  # 4 personas, 2 pasajeros
        r'para\s+(\d+)',  # para 4
        r'(\d+)\s*(?:adultos?|adults)',  # 4 adultos
    ]
    
    # Patterns for dates
    DATE_PATTERNS = [
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',  # DD/MM/YYYY
        r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',  # 15 de enero de 2025
    ]
    
    @classmethod
    def extract_tour_code(cls, message: str) -> Optional[str]:
        """
        Extract tour code from message.
        
        Args:
            message: Message text
            
        Returns:
            Tour code if found, None otherwise
        """
        message_upper = message.upper()
        
        for pattern in cls.TOUR_CODE_PATTERNS:
            match = re.search(pattern, message_upper, re.IGNORECASE)
            if match:
                code = match.group(1).upper()
                logger.info(f"Extracted tour code: {code}")
                return code
        
        return None
    
    @classmethod
    def extract_passengers(cls, message: str) -> Optional[int]:
        """
        Extract number of passengers from message.
        
        Args:
            message: Message text
            
        Returns:
            Number of passengers if found, None otherwise
        """
        for pattern in cls.PASSENGER_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                try:
                    count = int(match.group(1))
                    logger.info(f"Extracted passenger count: {count}")
                    return count
                except (ValueError, IndexError):
                    continue
        
        return None
    
    @classmethod
    def extract_date(cls, message: str) -> Optional[Dict[str, int]]:
        """
        Extract date from message.
        
        Args:
            message: Message text
            
        Returns:
            Dict with day, month, year if found, None otherwise
        """
        for pattern in cls.DATE_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                try:
                    if '/' in match.group(0) or '-' in match.group(0):
                        # DD/MM/YYYY format
                        day, month, year = match.groups()
                        return {
                            'day': int(day),
                            'month': int(month),
                            'year': int(year) if len(year) == 4 else 2000 + int(year)
                        }
                except (ValueError, IndexError):
                    continue
        
        return None
    
    @classmethod
    def is_reservation_message(cls, message: str) -> bool:
        """
        Check if message is a reservation request.
        
        Args:
            message: Message text
            
        Returns:
            True if message appears to be a reservation request
        """
        message_lower = message.lower()
        
        # Keywords that indicate reservation intent
        reservation_keywords = [
            'reservar', 'reserva', 'reservation',
            'tour', 'experiencia', 'experience',
            'disponibilidad', 'availability',
            'fecha', 'date', 'día', 'day'
        ]
        
        # Check if message contains tour code or reservation keywords
        has_tour_code = cls.extract_tour_code(message) is not None
        has_keywords = any(keyword in message_lower for keyword in reservation_keywords)
        
        return has_tour_code or has_keywords
    
    @classmethod
    def extract_reservation_code(cls, message: str) -> Optional[str]:
        """
        Extract reservation code (RES-XXX format) from message.
        
        Args:
            message: Message text
            
        Returns:
            Reservation code if found, None otherwise
        """
        # Pattern for RES-XXX-YYYYMMDD-XXXXXXXX format
        pattern = r'RES-([A-Z0-9-]+)'
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            code = match.group(0).upper()  # Get full match including RES- prefix
            logger.info(f"Extracted reservation code: {code}")
            return code
        return None
    
    @classmethod
    def parse_message(cls, message: str) -> Dict:
        """
        Parse message and extract all relevant information.
        
        Args:
            message: Message text
            
        Returns:
            Dict with extracted information
        """
        return {
            'tour_code': cls.extract_tour_code(message),
            'reservation_code': cls.extract_reservation_code(message),
            'passengers': cls.extract_passengers(message),
            'date': cls.extract_date(message),
            'is_reservation': cls.is_reservation_message(message),
            'original_message': message
        }

