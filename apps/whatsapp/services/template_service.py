"""
Template service facade - delegates to templates module.
"""
from typing import Optional
from .templates import TemplateRenderer


class TemplateService:
    """Facade for template rendering operations."""
    
    @classmethod
    def render_reservation_request(cls, reservation, code_obj=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'reservation_request', reservation, code_obj
        )
    
    @classmethod
    def render_customer_waiting(cls, reservation, code_obj=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'customer_waiting', reservation, code_obj
        )
    
    @classmethod
    def render_customer_confirmation(cls, reservation, code_obj=None, payment_link=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'customer_confirmation', reservation, code_obj, payment_link
        )
    
    @classmethod
    def render_customer_rejection(cls, reservation, code_obj=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'customer_rejection', reservation, code_obj
        )
    
    @classmethod
    def render_payment_link(cls, reservation, payment_link: str, code_obj=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'payment_link', reservation, code_obj, payment_link
        )
    
    @classmethod
    def render_payment_confirmed(cls, reservation, code_obj=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'payment_confirmed', reservation, code_obj
        )
    
    @classmethod
    def render_ticket_info(cls, reservation, code_obj=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'ticket_info', reservation, code_obj
        )
    
    @classmethod
    def render_reminder(cls, reservation, code_obj=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'reminder', reservation, code_obj
        )

    @classmethod
    def render_customer_availability_confirmed(cls, reservation, code_obj=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'customer_availability_confirmed', reservation, code_obj
        )

    @classmethod
    def render_customer_confirm_free(cls, reservation, code_obj=None) -> str:
        return TemplateRenderer.render_message(
            reservation.operator, 'customer_confirm_free', reservation, code_obj
        )
