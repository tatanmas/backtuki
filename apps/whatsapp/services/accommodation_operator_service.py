"""
Service for Accommodation-Operator-Group bindings.

Mirrors ExperienceOperatorService: resolves WhatsApp group and operator for an
accommodation (used by WhatsApp reservation flow).
"""
import logging
from typing import Optional
from django.db import transaction

from apps.whatsapp.models import (
    TourOperator,
    AccommodationOperatorBinding,
    AccommodationGroupBinding,
)
from apps.accommodations.models import Accommodation

logger = logging.getLogger(__name__)


class AccommodationOperatorService:
    """Service for resolving operator and WhatsApp group for accommodations."""

    @staticmethod
    def get_accommodation_whatsapp_group(accommodation: Accommodation) -> Optional[dict]:
        """
        Get the WhatsApp group for an accommodation (bindings and operator defaults).

        Args:
            accommodation: The Accommodation instance

        Returns:
            Dict with group info (id, chat_id, name, operator) or None
        """
        if not accommodation:
            return None

        # Override binding first
        active_binding = accommodation.whatsapp_group_bindings.filter(
            is_active=True,
            is_override=True,
        ).select_related("whatsapp_group", "tour_operator").first()

        if active_binding and active_binding.whatsapp_group:
            group = active_binding.whatsapp_group
            op = active_binding.tour_operator or getattr(group, "assigned_operator", None)
            return {
                "id": str(group.id),
                "chat_id": group.chat_id,
                "name": group.name,
                "is_override": True,
                "source": "custom_binding",
                "operator": op,
            }

        # Operator default group
        operator_binding = accommodation.operator_bindings.filter(is_active=True).first()
        if operator_binding and operator_binding.tour_operator:
            operator = operator_binding.tour_operator
            if operator.default_whatsapp_group:
                return {
                    "id": str(operator.default_whatsapp_group.id),
                    "chat_id": operator.default_whatsapp_group.chat_id,
                    "name": operator.default_whatsapp_group.name,
                    "is_override": False,
                    "source": "operator_default",
                    "operator": operator,
                }

        # Non-override binding
        default_binding = accommodation.whatsapp_group_bindings.filter(
            is_active=True,
            is_override=False,
        ).select_related("whatsapp_group", "tour_operator").first()

        if default_binding and default_binding.whatsapp_group:
            group = default_binding.whatsapp_group
            op = default_binding.tour_operator or getattr(group, "assigned_operator", None)
            return {
                "id": str(group.id),
                "chat_id": group.chat_id,
                "name": group.name,
                "is_override": False,
                "source": "default_binding",
                "operator": op,
            }

        return None

    @staticmethod
    @transaction.atomic
    def create_accommodation_group_binding(
        accommodation: Accommodation,
        whatsapp_group_id: str,
        tour_operator: Optional[TourOperator] = None,
        is_override: bool = True,
    ) -> Optional[AccommodationGroupBinding]:
        """Create or update AccommodationGroupBinding."""
        from apps.whatsapp.models import WhatsAppChat

        if not accommodation:
            raise ValueError("Accommodation is required")
        try:
            whatsapp_group = WhatsAppChat.objects.get(id=whatsapp_group_id, type="group")
        except WhatsAppChat.DoesNotExist:
            logger.warning("WhatsApp group %s not found", whatsapp_group_id)
            return None

        binding, created = AccommodationGroupBinding.objects.update_or_create(
            accommodation=accommodation,
            defaults={
                "whatsapp_group": whatsapp_group,
                "tour_operator": tour_operator,
                "is_active": True,
                "is_override": is_override,
            },
        )
        action = "Created" if created else "Updated"
        logger.info(
            "%s AccommodationGroupBinding for '%s' -> group '%s'",
            action,
            accommodation.title,
            whatsapp_group.name,
        )
        return binding
