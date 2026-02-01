"""Reservation code generator with secure hash-based codes."""
import secrets
import hashlib
from datetime import datetime, timedelta
from django.utils import timezone
from apps.experiences.models import Experience
from apps.whatsapp.models import WhatsAppReservationCode


class ReservationCodeGenerator:
    """Generate unique, secure reservation codes."""
    
    DEFAULT_EXPIRY_HOURS = 24
    
    @staticmethod
    def generate_code(experience_id, checkout_data):
        """
        Generate a unique, secure reservation code.
        
        Args:
            experience_id: UUID of the Experience
            checkout_data: Dict with participants, date, time, pricing, etc.
            
        Returns:
            WhatsAppReservationCode instance
        """
        try:
            experience = Experience.objects.get(id=experience_id)
        except Experience.DoesNotExist:
            raise ValueError(f"Experience {experience_id} not found")
        
        # Generate secure code using hash
        experience_slug = (experience.slug[:6] if experience.slug else 'EXP').upper()
        date_str = datetime.now().strftime('%Y%m%d')
        
        # Create unique input for hash
        unique_id = secrets.token_urlsafe(16)
        hash_input = f"{experience_id}-{unique_id}-{timezone.now().isoformat()}"
        hash_suffix = hashlib.sha256(hash_input.encode()).hexdigest()[:8].upper()
        
        code = f"RES-{experience_slug}-{date_str}-{hash_suffix}"
        
        # Ensure uniqueness (retry if collision)
        max_retries = 10
        retries = 0
        while WhatsAppReservationCode.objects.filter(code=code).exists() and retries < max_retries:
            unique_id = secrets.token_urlsafe(16)
            hash_input = f"{experience_id}-{unique_id}-{timezone.now().isoformat()}"
            hash_suffix = hashlib.sha256(hash_input.encode()).hexdigest()[:8].upper()
            code = f"RES-{experience_slug}-{date_str}-{hash_suffix}"
            retries += 1
        
        if retries >= max_retries:
            raise ValueError("Could not generate unique code after multiple attempts")
        
        # Calculate expiry (24 hours from now)
        expires_at = timezone.now() + timedelta(hours=ReservationCodeGenerator.DEFAULT_EXPIRY_HOURS)
        
        # Create code object
        code_obj = WhatsAppReservationCode.objects.create(
            code=code,
            experience=experience,
            checkout_data=checkout_data,
            status='pending',
            expires_at=expires_at
        )
        
        return code_obj
    
    @staticmethod
    def validate_code(code):
        """
        Validate a reservation code.
        
        Args:
            code: Reservation code string
            
        Returns:
            WhatsAppReservationCode instance if valid, None otherwise
        """
        try:
            code_obj = WhatsAppReservationCode.objects.get(
                code=code,
                status='pending',
                expires_at__gt=timezone.now()
            )
            return code_obj
        except WhatsAppReservationCode.DoesNotExist:
            return None

