"""Context builder for template variables."""
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime


class ContextBuilder:
    """Builds context dictionaries for template rendering."""
    
    MONTHS_ES = {
        1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
        5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
        9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
    }
    
    @classmethod
    def format_price(cls, amount, currency: str = 'CLP') -> str:
        """Format price with currency symbol."""
        try:
            amount = Decimal(str(amount))
            if currency == 'CLP':
                return f"${int(amount):,}".replace(',', '.')
            elif currency == 'USD':
                return f"${amount:,.2f}"
            return f"{amount} {currency}"
        except (ValueError, TypeError):
            return str(amount)
    
    @classmethod
    def format_date(cls, dt: datetime) -> str:
        """Format date in Spanish."""
        return f"{dt.day} de {cls.MONTHS_ES[dt.month]} de {dt.year}"
    
    @classmethod
    def format_time(cls, dt: datetime) -> str:
        """Format time as HH:MM."""
        return dt.strftime('%H:%M')
    
    @classmethod
    def parse_datetime(cls, date_str: str) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if not date_str:
            return None
        try:
            if 'T' in date_str:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return datetime.strptime(date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            return None
    
    @classmethod
    def build(
        cls,
        reservation,
        code_obj=None,
        payment_link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build context from reservation and related objects."""
        context = {}
        
        # Operator info (nullable when experience has no operator assigned)
        operator = reservation.operator
        context['contacto'] = (operator.contact_name or operator.name) if operator else 'Operador'
        
        # Experience info
        exp = reservation.experience
        if exp:
            context['experiencia'] = exp.title
            context['punto_encuentro'] = exp.location_name or 'Por confirmar'
            context['instrucciones'] = exp.short_description or ''
        else:
            context['experiencia'] = 'Experiencia'
            context['punto_encuentro'] = 'Por confirmar'
            context['instrucciones'] = ''
        
        # Checkout data
        checkout = code_obj.checkout_data if code_obj else {}
        
        # Date and time
        date_str = checkout.get('date', '')
        dt = cls.parse_datetime(date_str)
        context['fecha'] = cls.format_date(dt) if dt else checkout.get('date', 'Por confirmar')
        context['hora'] = checkout.get('time') or (cls.format_time(dt) if dt else 'Por confirmar')
        
        # Participants
        participants = checkout.get('participants', {})
        adults = participants.get('adults', reservation.passengers or 1)
        children = participants.get('children', 0)
        infants = participants.get('infants', 0)
        
        context['pasajeros'] = str(adults + children + infants)
        context['adultos'] = str(adults)
        context['ninos'] = str(children)
        context['infantes'] = str(infants)
        
        # Pricing
        pricing = checkout.get('pricing', {})
        context['precio'] = cls.format_price(
            pricing.get('total', 0),
            pricing.get('currency', 'CLP')
        )
        
        # Customer info
        customer = checkout.get('customer', {})
        context['nombre_cliente'] = customer.get('name', 'Cliente')
        msg = reservation.whatsapp_message
        context['telefono_cliente'] = customer.get('phone', msg.phone if msg else '')
        
        # Code
        context['codigo'] = reservation.tour_code
        
        # Payment
        if payment_link:
            context['link_pago'] = payment_link
            context['link_pago_mensaje'] = f"\nPara completar: {payment_link}"
        else:
            context['link_pago'] = ''
            context['link_pago_mensaje'] = ''

        # Pasos siguientes (for availability_confirmed)
        try:
            total = float(
                pricing.get('total') or
                checkout.get('total_price') or
                0
            )
        except (TypeError, ValueError):
            total = 0
        if total > 0:
            context['pasos_siguientes'] = (
                "Para completar su reserva debe realizar el pago. "
                "Le enviaremos el enlace en el siguiente mensaje."
            )
        else:
            context['pasos_siguientes'] = "Para confirmar responda SI."
        
        return context
