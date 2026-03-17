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
        
        # Product info (experience, accommodation or car_rental)
        exp = reservation.experience
        acc = getattr(reservation, 'accommodation', None)
        car = getattr(reservation, 'car', None)
        if exp:
            context['experiencia'] = exp.title
            context['punto_encuentro'] = exp.location_name or 'Por confirmar'
            context['instrucciones'] = exp.short_description or ''
        elif acc:
            context['experiencia'] = acc.title
            context['punto_encuentro'] = (acc.location_name or acc.location_address or 'Por confirmar')[:200]
            context['instrucciones'] = (acc.short_description or '')[:200]
        elif car:
            context['experiencia'] = car.title
            context['punto_encuentro'] = (getattr(car.company, 'name', '') or 'Por confirmar')[:200]
            context['instrucciones'] = (car.short_description or '')[:200]
        else:
            context['experiencia'] = 'Reserva'
            context['punto_encuentro'] = 'Por confirmar'
            context['instrucciones'] = ''

        # Checkout data
        checkout = code_obj.checkout_data if code_obj else {}
        guide_context = checkout.get('travel_guide_context') if isinstance(checkout, dict) else {}
        if not isinstance(guide_context, dict):
            guide_context = {}

        # Date and time (for accommodation: check_in/check_out)
        date_str = checkout.get('date', '')
        dt = cls.parse_datetime(date_str)
        context['fecha'] = cls.format_date(dt) if dt else checkout.get('date', 'Por confirmar')
        context['hora'] = checkout.get('time') or (cls.format_time(dt) if dt else 'Por confirmar')
        if checkout.get('check_in'):
            context['check_in'] = checkout.get('check_in')
            context['check_out'] = checkout.get('check_out', '')
        else:
            context['check_in'] = ''
            context['check_out'] = ''
        context['pickup_date'] = checkout.get('pickup_date', '')
        context['return_date'] = checkout.get('return_date', '')
        context['pickup_time'] = checkout.get('pickup_time', '')
        context['return_time'] = checkout.get('return_time', '')
        context['guests'] = checkout.get('guests', 1)

        # Accommodation: override with linked_accommodation_reservation when present (source of truth for total and dates)
        acc_res = getattr(reservation, 'linked_accommodation_reservation', None)
        if acc_res is not None:
            context['precio'] = cls.format_price(
                getattr(acc_res, 'total', 0) or 0,
                getattr(acc_res, 'currency', None) or 'CLP'
            )
            if getattr(acc_res, 'check_in', None):
                context['check_in'] = acc_res.check_in.isoformat() if hasattr(acc_res.check_in, 'isoformat') else str(acc_res.check_in)
                try:
                    from datetime import date
                    d = acc_res.check_in if isinstance(acc_res.check_in, date) else cls.parse_datetime(context['check_in'])
                    context['fecha'] = cls.format_date(d) if d else context['check_in']
                except Exception:
                    context['fecha'] = context['check_in']
            if getattr(acc_res, 'check_out', None):
                context['check_out'] = acc_res.check_out.isoformat() if hasattr(acc_res.check_out, 'isoformat') else str(acc_res.check_out)
                context['hora'] = context['check_out']
            if getattr(acc_res, 'guests', None) is not None:
                context['guests'] = int(acc_res.guests)
                context['pasajeros'] = str(acc_res.guests)
            # Optional: formatted breakdown for templates (e.g. comprobante con desglose)
            snapshot = getattr(acc_res, 'pricing_snapshot', None)
            if isinstance(snapshot, dict) and snapshot.get('extras'):
                lines = []
                base = snapshot.get('base', {})
                if base:
                    lines.append(f"Alojamiento ({snapshot.get('nights', 0)} noches): {cls.format_price(base.get('subtotal', 0), snapshot.get('currency', 'CLP'))}")
                for e in snapshot.get('extras', []):
                    lines.append(f"{e.get('name', e.get('code', ''))}: {cls.format_price(e.get('total', 0), snapshot.get('currency', 'CLP'))}")
                context['desglose_precio'] = '\n'.join(lines)
            else:
                context['desglose_precio'] = ''
        
        if not acc_res:
            # Participants (experience/car) from checkout
            participants = checkout.get('participants', {})
            adults = participants.get('adults', reservation.passengers or 1)
            children = participants.get('children', 0)
            infants = participants.get('infants', 0)
            context['pasajeros'] = str(adults + children + infants)
            context['adultos'] = str(adults)
            context['ninos'] = str(children)
            context['infantes'] = str(infants)
        else:
            context['adultos'] = context.get('pasajeros', '0')
            context['ninos'] = '0'
            context['infantes'] = '0'

        # Pricing (only when not overridden by accommodation)
        if acc_res is None:
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
        context['guia_viaje'] = str(guide_context.get('guide_title') or '').strip()
        context['slot_guia'] = str(guide_context.get('slot_label') or '').strip()
        if context['guia_viaje']:
            context['experiencia'] = f"[Guía {context['guia_viaje']}] {context['experiencia']}"
        
        # Payment
        if payment_link:
            context['link_pago'] = payment_link
            context['link_pago_mensaje'] = f"\nPara completar: {payment_link}"
        else:
            context['link_pago'] = ''
            context['link_pago_mensaje'] = ''

        # Pasos siguientes (for availability_confirmed)
        try:
            if acc_res is not None:
                total = float(getattr(acc_res, 'total', 0) or 0)
            else:
                pricing = checkout.get('pricing', {})
                total = float(pricing.get('total') or checkout.get('total_price') or 0)
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
