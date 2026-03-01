"""
Service for Car (car_rental) - Operator - Group bindings.

Resolves WhatsApp group and operator for a car (used by WhatsApp reservation flow).
"""
import logging
from typing import Optional

from apps.whatsapp.models import CarOperatorBinding, CarGroupBinding
from apps.car_rental.models import Car

logger = logging.getLogger(__name__)


class CarOperatorService:
    """Service for resolving operator and WhatsApp group for cars (car_rental)."""

    @staticmethod
    def get_car_whatsapp_group(car: Car) -> Optional[dict]:
        """
        Get the WhatsApp group for a car (bindings and operator defaults).

        Args:
            car: The Car instance

        Returns:
            Dict with group info (id, chat_id, name, operator) or None
        """
        if not car:
            return None

        # Override binding first
        active_binding = car.whatsapp_group_bindings.filter(
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
        operator_binding = car.operator_bindings.filter(is_active=True).first()
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
        default_binding = car.whatsapp_group_bindings.filter(
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
