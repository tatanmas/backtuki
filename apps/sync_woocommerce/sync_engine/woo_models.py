"""
Modelos de datos para el sincronizador
Define estructuras de datos para órdenes, tickets y eventos
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
import json

@dataclass
class WooCommerceOrder:
    """Modelo para órdenes de WooCommerce"""
    order_id: int
    order_date: datetime
    order_status: str
    
    # Información financiera
    order_currency: str = "CLP"
    order_total: Optional[Decimal] = None
    order_tax: Optional[Decimal] = None
    order_shipping: Optional[Decimal] = None
    order_shipping_tax: Optional[Decimal] = None
    cart_discount: Optional[Decimal] = None
    cart_discount_tax: Optional[Decimal] = None
    total_refunded: Optional[Decimal] = None
    net_paid: Optional[Decimal] = None
    
    # Información de pago
    payment_method: Optional[str] = None
    payment_method_title: Optional[str] = None
    transaction_id: Optional[str] = None
    order_key: Optional[str] = None
    
    # Fechas importantes
    date_paid_ts: Optional[str] = None
    date_completed_ts: Optional[str] = None
    completed_date: Optional[str] = None
    
    # Información del cliente
    customer_user_id: Optional[int] = None
    customer_ip_address: Optional[str] = None
    customer_user_agent: Optional[str] = None
    
    # Información de facturación
    billing_email: Optional[str] = None
    billing_first_name: Optional[str] = None
    billing_last_name: Optional[str] = None
    billing_address_1: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_postcode: Optional[str] = None
    billing_country: Optional[str] = None
    billing_phone: Optional[str] = None
    
    # Información de envío
    shipping_first_name: Optional[str] = None
    shipping_last_name: Optional[str] = None
    shipping_address_1: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_postcode: Optional[str] = None
    shipping_country: Optional[str] = None
    
    # Productos y cupones
    product_ids: List[int] = field(default_factory=list)
    variation_ids: List[int] = field(default_factory=list)
    total_qty: int = 0
    coupon_codes: List[str] = field(default_factory=list)
    coupons_discount_sum: Optional[Decimal] = None
    
    # Flags operativos
    created_via: Optional[str] = None
    prices_include_tax: Optional[bool] = None
    download_permissions_granted: Optional[bool] = None
    order_stock_reduced: Optional[bool] = None
    new_order_email_sent: Optional[bool] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WooCommerceOrder':
        """Crea una instancia desde un diccionario de datos MySQL"""
        
        # Convertir fechas
        order_date = data.get('order_date')
        if isinstance(order_date, str):
            order_date = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
        elif order_date is None:
            order_date = datetime.now()
        
        # Convertir decimales
        def to_decimal(value):
            if value is None or value == '':
                return None
            try:
                return Decimal(str(value))
            except:
                return None
        
        # Convertir enteros (maneja decimales también)
        def to_int(value):
            if value is None or value == '':
                return None
            try:
                # Si es un decimal, convertir a float primero, luego a int
                if '.' in str(value):
                    return int(float(str(value)))
                return int(str(value))
            except:
                return None
        
        # Convertir listas de IDs
        def parse_id_list(value):
            if not value:
                return []
            try:
                return [int(x.strip()) for x in str(value).split(',') if x.strip().isdigit()]
            except:
                return []
        
        # Convertir lista de cupones
        def parse_coupon_list(value):
            if not value:
                return []
            try:
                return [x.strip() for x in str(value).split(',') if x.strip()]
            except:
                return []
        
        # Convertir booleanos
        def to_bool(value):
            if value is None or value == '':
                return None
            return str(value).lower() in ('1', 'yes', 'true')
        
        return cls(
            order_id=int(data['order_id']),
            order_date=order_date,
            order_status=data.get('order_status', ''),
            
            # Financiero
            order_currency=data.get('order_currency', 'CLP'),
            order_total=to_decimal(data.get('order_total')),
            order_tax=to_decimal(data.get('order_tax')),
            order_shipping=to_decimal(data.get('order_shipping')),
            order_shipping_tax=to_decimal(data.get('order_shipping_tax')),
            cart_discount=to_decimal(data.get('cart_discount')),
            cart_discount_tax=to_decimal(data.get('cart_discount_tax')),
            total_refunded=to_decimal(data.get('total_refunded')),
            net_paid=to_decimal(data.get('net_paid')),
            
            # Pago
            payment_method=data.get('payment_method'),
            payment_method_title=data.get('payment_method_title'),
            transaction_id=data.get('transaction_id'),
            order_key=data.get('order_key'),
            
            # Fechas
            date_paid_ts=data.get('date_paid_ts'),
            date_completed_ts=data.get('date_completed_ts'),
            completed_date=data.get('completed_date'),
            
            # Cliente
            customer_user_id=to_int(data.get('customer_user_id')),
            customer_ip_address=data.get('customer_ip_address'),
            customer_user_agent=data.get('customer_user_agent'),
            
            # Facturación
            billing_email=data.get('billing_email'),
            billing_first_name=data.get('billing_first_name'),
            billing_last_name=data.get('billing_last_name'),
            billing_address_1=data.get('billing_address_1'),
            billing_city=data.get('billing_city'),
            billing_state=data.get('billing_state'),
            billing_postcode=data.get('billing_postcode'),
            billing_country=data.get('billing_country'),
            billing_phone=data.get('billing_phone'),
            
            # Envío
            shipping_first_name=data.get('shipping_first_name'),
            shipping_last_name=data.get('shipping_last_name'),
            shipping_address_1=data.get('shipping_address_1'),
            shipping_city=data.get('shipping_city'),
            shipping_state=data.get('shipping_state'),
            shipping_postcode=data.get('shipping_postcode'),
            shipping_country=data.get('shipping_country'),
            
            # Productos
            product_ids=parse_id_list(data.get('product_ids')),
            variation_ids=parse_id_list(data.get('variation_ids')),
            total_qty=to_int(data.get('total_qty')) or 0,
            coupon_codes=parse_coupon_list(data.get('coupon_codes')),
            coupons_discount_sum=to_decimal(data.get('coupons_discount_sum')),
            
            # Flags
            created_via=data.get('created_via'),
            prices_include_tax=to_bool(data.get('prices_include_tax')),
            download_permissions_granted=to_bool(data.get('download_permissions_granted')),
            order_stock_reduced=to_bool(data.get('order_stock_reduced')),
            new_order_email_sent=to_bool(data.get('new_order_email_sent')),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la instancia a diccionario para serialización"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Decimal):
                result[key] = float(value) if value is not None else None
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result

@dataclass
class EventTicket:
    """Modelo para tickets de eventos (event_magic_tickets)"""
    ticket_post_id: int
    ticket_created: datetime
    ticket_id: str
    order_id: int
    product_id: int
    variation_id: Optional[int] = None
    
    # Datos del asistente
    attendee_first_name: Optional[str] = None
    attendee_last_name: Optional[str] = None
    attendee_email: Optional[str] = None
    
    # Datos del comprador
    purchaser_first_name: Optional[str] = None
    purchaser_last_name: Optional[str] = None
    purchaser_email: Optional[str] = None
    
    # Campos personalizados del formulario (Custom Attendee Fields)
    custom_attendee_fields: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EventTicket':
        """Crea una instancia desde un diccionario de datos MySQL"""
        
        # Convertir fecha de creación del ticket
        ticket_created = data.get('ticket_created')
        if isinstance(ticket_created, str):
            try:
                ticket_created = datetime.fromisoformat(ticket_created.replace('Z', '+00:00'))
            except:
                ticket_created = datetime.now()
        elif ticket_created is None:
            ticket_created = datetime.now()
        
        # Función auxiliar para convertir enteros
        def to_int_safe(value, default=0):
            if value is None or value == '':
                return default
            try:
                if '.' in str(value):
                    return int(float(str(value)))
                return int(str(value))
            except:
                return default
        
        return cls(
            ticket_post_id=to_int_safe(data['ticket_post_id']),
            ticket_created=ticket_created,
            ticket_id=data.get('ticket_id', ''),
            order_id=to_int_safe(data['order_id']),
            product_id=to_int_safe(data['product_id']),
            variation_id=to_int_safe(data.get('variation_id')) if data.get('variation_id') else None,
            
            # Datos del asistente
            attendee_first_name=data.get('attendee_first_name'),
            attendee_last_name=data.get('attendee_last_name'),
            attendee_email=data.get('attendee_email'),
            
            # Datos del comprador
            purchaser_first_name=data.get('purchaser_first_name'),
            purchaser_last_name=data.get('purchaser_last_name'),
            purchaser_email=data.get('purchaser_email'),
            
            # Campos personalizados (parsear JSON si existe)
            custom_attendee_fields=cls._parse_custom_fields(data.get('custom_attendee_fields'))
        )
    
    @staticmethod
    def _parse_custom_fields(custom_fields_json: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Parsea el JSON de campos personalizados
        
        Args:
            custom_fields_json: String JSON con los campos personalizados o None
            
        Returns:
            Dict con los campos parseados o None si no hay datos
        """
        # Si es None o vacío, retornar None
        if not custom_fields_json:
            return None
        
        # Si ya es un diccionario (viene parseado de MySQL JSON), devolverlo directamente
        if isinstance(custom_fields_json, dict):
            return custom_fields_json if custom_fields_json else None
        
        # Si es string, intentar parsearlo
        if isinstance(custom_fields_json, str):
            if custom_fields_json.strip() == '':
                return None
            
            try:
                import json
                parsed_fields = json.loads(custom_fields_json)
                
                # Si es un diccionario válido, devolverlo
                if isinstance(parsed_fields, dict):
                    return parsed_fields if parsed_fields else None
                else:
                    # Si no es un dict, convertir a string
                    return {"raw_data": str(parsed_fields)}
                    
            except (json.JSONDecodeError, TypeError) as e:
                # Si falla el parsing, guardar como string raw
                return {"raw_data": str(custom_fields_json), "parse_error": str(e)}
        
        # Para cualquier otro tipo, convertir a string
        return {"raw_data": str(custom_fields_json)}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la instancia a diccionario"""
        result = self.__dict__.copy()
        if isinstance(result['ticket_created'], datetime):
            result['ticket_created'] = result['ticket_created'].isoformat()
        return result

@dataclass
class ProductInfo:
    """Modelo para información de productos/eventos"""
    product_id: int
    product_name: str
    product_description: Optional[str] = None
    product_status: str = "publish"
    created_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProductInfo':
        """Crea una instancia desde un diccionario de datos MySQL"""
        
        def parse_date(date_value):
            if isinstance(date_value, str):
                try:
                    return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                except:
                    return None
            return date_value
        
        # Función auxiliar para convertir enteros
        def to_int_safe(value):
            if value is None or value == '':
                return 0
            try:
                if '.' in str(value):
                    return int(float(str(value)))
                return int(str(value))
            except:
                return 0
        
        return cls(
            product_id=to_int_safe(data['product_id']),
            product_name=data.get('product_name', ''),
            product_description=data.get('product_description'),
            product_status=data.get('product_status', 'publish'),
            created_date=parse_date(data.get('created_date')),
            modified_date=parse_date(data.get('modified_date'))
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la instancia a diccionario"""
        result = self.__dict__.copy()
        for key, value in result.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat() if value else None
        return result

@dataclass
class EventSyncData:
    """Modelo completo para datos de sincronización de un evento"""
    product_info: ProductInfo
    orders: List[WooCommerceOrder] = field(default_factory=list)
    tickets: List[EventTicket] = field(default_factory=list)
    
    # Estadísticas calculadas
    total_orders: int = 0
    total_tickets: int = 0
    total_revenue: Decimal = field(default_factory=lambda: Decimal('0'))
    unique_customers: int = 0
    
    def calculate_stats(self):
        """Calcula estadísticas del evento"""
        self.total_orders = len(self.orders)
        self.total_tickets = len(self.tickets)  # Ahora contamos tickets reales
        self.total_revenue = sum(
            (order.net_paid or Decimal('0')) for order in self.orders
        )
        
        # Contar clientes únicos por email
        unique_emails = set()
        for order in self.orders:
            if order.billing_email:
                unique_emails.add(order.billing_email.lower())
        self.unique_customers = len(unique_emails)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para serialización"""
        return {
            'product_info': self.product_info.to_dict(),
            'orders': [order.to_dict() for order in self.orders],
            'tickets': [ticket.to_dict() for ticket in self.tickets],
            'stats': {
                'total_orders': self.total_orders,
                'total_tickets': self.total_tickets,
                'total_revenue': float(self.total_revenue),
                'unique_customers': self.unique_customers
            }
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convierte a JSON string"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

@dataclass
class SyncResult:
    """Resultado de una operación de sincronización"""
    success: bool
    product_id: int
    event_data: Optional[EventSyncData] = None
    error_message: Optional[str] = None
    execution_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        result = {
            'success': self.success,
            'product_id': self.product_id,
            'error_message': self.error_message,
            'execution_time': self.execution_time,
            'timestamp': self.timestamp.isoformat()
        }
        
        if self.event_data:
            result['event_data'] = self.event_data.to_dict()
        
        return result
