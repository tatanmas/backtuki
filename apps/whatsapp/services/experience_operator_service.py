"""
Service for managing TourOperator creation and Experience-Operator-Group bindings.

This service handles:
- Auto-creation of TourOperators when Organizers create Experiences
- Creation of ExperienceGroupBindings when Experiences are created
- Linking Experiences to WhatsApp Groups via TourOperators
"""
import logging
from typing import Optional, Tuple
from django.db import transaction
from apps.whatsapp.models import TourOperator, ExperienceGroupBinding
from apps.organizers.models import Organizer
from apps.experiences.models import Experience

logger = logging.getLogger(__name__)


class ExperienceOperatorService:
    """Service for managing Experience-Operator relationships."""
    
    @staticmethod
    def get_or_create_operator_for_organizer(organizer: Organizer) -> Tuple[TourOperator, bool]:
        """
        Get or create a TourOperator for an Organizer.
        
        Args:
            organizer: The Organizer instance
            
        Returns:
            Tuple of (TourOperator, created: bool)
        """
        if not organizer:
            raise ValueError("Organizer is required")
        
        tour_operator, created = TourOperator.objects.get_or_create(
            organizer=organizer,
            defaults={
                'name': organizer.name,
                'contact_name': organizer.representative_name or '',
                'contact_phone': organizer.representative_phone or '',
                'contact_email': organizer.representative_email or '',
                'is_system_created': True,
                'is_active': True
            }
        )
        
        if created:
            logger.info(f"✅ Auto-created TourOperator '{tour_operator.name}' for organizer '{organizer.name}'")
        else:
            logger.debug(f"ℹ️ Using existing TourOperator '{tour_operator.name}' for organizer '{organizer.name}'")
        
        return tour_operator, created
    
    @staticmethod
    @transaction.atomic
    def create_experience_group_binding(
        experience: Experience,
        tour_operator: Optional[TourOperator] = None,
        whatsapp_group_id: Optional[str] = None,
        is_override: bool = False
    ) -> Optional[ExperienceGroupBinding]:
        """
        Create an ExperienceGroupBinding for an Experience.
        
        Args:
            experience: The Experience instance
            tour_operator: Optional TourOperator (will try to get from experience if not provided)
            whatsapp_group_id: Optional WhatsApp group ID (will use operator default if not provided)
            is_override: Whether this binding overrides the operator default
            
        Returns:
            ExperienceGroupBinding instance or None if no group available
        """
        if not experience:
            raise ValueError("Experience is required")
        
        # Get operator from experience if not provided
        if not tour_operator:
            operator_binding = experience.operator_bindings.filter(is_active=True).first()
            if operator_binding:
                tour_operator = operator_binding.tour_operator
        
        # Determine which group to use
        whatsapp_group = None
        
        if whatsapp_group_id:
            # Use specified group
            from apps.whatsapp.models import WhatsAppChat
            try:
                whatsapp_group = WhatsAppChat.objects.get(id=whatsapp_group_id, type='group')
            except WhatsAppChat.DoesNotExist:
                logger.warning(f"WhatsApp group {whatsapp_group_id} not found")
                return None
        elif tour_operator and tour_operator.default_whatsapp_group:
            # Use operator's default group
            whatsapp_group = tour_operator.default_whatsapp_group
            is_override = False  # Not an override if using default
        
        if not whatsapp_group:
            logger.debug(f"No WhatsApp group available for experience '{experience.title}'")
            return None
        
        # Create or update binding
        binding, created = ExperienceGroupBinding.objects.update_or_create(
            experience=experience,
            defaults={
                'whatsapp_group': whatsapp_group,
                'tour_operator': tour_operator,
                'is_active': True,
                'is_override': is_override
            }
        )
        
        action = 'Created' if created else 'Updated'
        logger.info(
            f"✅ {action} ExperienceGroupBinding for '{experience.title}' -> "
            f"group '{whatsapp_group.name}' (override: {is_override})"
        )
        
        return binding
    
    @staticmethod
    def get_experience_whatsapp_group(experience: Experience) -> Optional[dict]:
        """
        Get the WhatsApp group for an experience, considering bindings and operator defaults.
        
        Args:
            experience: The Experience instance
            
        Returns:
            Dict with group info or None if no group available
        """
        # Check for active custom binding first
        active_binding = experience.whatsapp_group_bindings.filter(
            is_active=True,
            is_override=True
        ).first()
        
        if active_binding and active_binding.whatsapp_group:
            return {
                'id': str(active_binding.whatsapp_group.id),
                'chat_id': active_binding.whatsapp_group.chat_id,
                'name': active_binding.whatsapp_group.name,
                'is_override': True,
                'source': 'custom_binding'
            }
        
        # Check for operator default group
        operator_binding = experience.operator_bindings.filter(is_active=True).first()
        if operator_binding and operator_binding.tour_operator:
            operator = operator_binding.tour_operator
            if operator.default_whatsapp_group:
                return {
                    'id': str(operator.default_whatsapp_group.id),
                    'chat_id': operator.default_whatsapp_group.chat_id,
                    'name': operator.default_whatsapp_group.name,
                    'is_override': False,
                    'source': 'operator_default'
                }
        
        # Check for non-override binding (legacy)
        default_binding = experience.whatsapp_group_bindings.filter(
            is_active=True,
            is_override=False
        ).first()
        
        if default_binding and default_binding.whatsapp_group:
            return {
                'id': str(default_binding.whatsapp_group.id),
                'chat_id': default_binding.whatsapp_group.chat_id,
                'name': default_binding.whatsapp_group.name,
                'is_override': False,
                'source': 'default_binding'
            }
        
        return None
    
    @staticmethod
    @transaction.atomic
    def remove_experience_group_binding(experience: Experience, only_overrides: bool = True) -> bool:
        """
        Remove group binding(s) for an experience.
        
        Args:
            experience: The Experience instance
            only_overrides: If True, only remove override bindings (default: True)
            
        Returns:
            True if bindings were removed, False otherwise
        """
        if not experience:
            raise ValueError("Experience is required")
        
        if only_overrides:
            bindings = experience.whatsapp_group_bindings.filter(
                is_active=True,
                is_override=True
            )
        else:
            bindings = experience.whatsapp_group_bindings.filter(is_active=True)
        
        count = bindings.count()
        if count > 0:
            bindings.update(is_active=False)
            logger.info(f"✅ Removed {count} group binding(s) for experience '{experience.title}'")
            return True
        
        return False

