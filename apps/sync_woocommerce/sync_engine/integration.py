"""
Módulo de integración para migrar datos de WooCommerce al backend Django.

Este módulo maneja:
1. Mapeo de datos entre WooCommerce y Django
2. Cálculo de división de totales (cargo servicio vs organizador)
3. Creación de eventos, órdenes y tickets
4. Generación de formularios personalizados
5. Creación automática de organizadores
"""

import logging
import json
import requests
from decimal import Decimal, ROUND_UP
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

# Django imports para ORM directo
from django.utils import timezone
from django.utils.text import slugify
from apps.organizers.models import Organizer, OrganizerUser
from apps.events.models import Event
from apps.forms.models import Form, FormField, FieldOption
from apps.events.models import Order, Ticket, OrderItem, TicketTier
from apps.users.models import User
from django.db import transaction
from django.contrib.auth.hashers import make_password
import secrets
import string

logger = logging.getLogger(__name__)


@dataclass
class IntegrationConfig:
    """Configuración para la integración con el backend Django"""
    backend_url: str = "http://localhost:8000"  # URL del backend Django
    api_token: str = ""  # Token de autenticación
    default_service_fee_percentage: Decimal = Decimal('10.0')  # 10% por defecto
    default_currency: str = "CLP"
    timeout: int = 30


@dataclass
class EventMigrationRequest:
    """Datos necesarios para migrar un evento"""
    event_name: str
    organizer_email: str
    organizer_name: str = ""
    service_fee_percentage: Optional[Decimal] = None
    event_description: str = ""
    event_start_date: Optional[str] = None
    event_end_date: Optional[str] = None
    location_name: str = ""
    location_address: str = ""


class WooCommerceToDjangoMapper:
    """Mapea datos de WooCommerce a estructuras Django"""
    
    def __init__(self, config: IntegrationConfig):
        self.config = config
    
    def map_event_data(self, woo_data: Dict[str, Any], migration_request: EventMigrationRequest) -> Dict[str, Any]:
        """
        Mapea datos del producto WooCommerce a un evento Django
        
        Args:
            woo_data: Datos extraídos de WooCommerce
            migration_request: Configuración de migración
            
        Returns:
            Dict con datos mapeados para crear evento Django
        """
        product_info = woo_data['product_info']
        
        # 🎯 EXTRAER FECHA REAL DEL EVENTO desde la descripción de WooCommerce
        start_date = None
        end_date = None
        
        # 1️⃣ PRIORIDAD: Extraer fecha de la descripción del producto
        description = product_info.get('product_description', '')
        if description:
            import re
            
            # Mapeo de meses en español a números
            meses_es = {
                'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
                'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
                'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
            }
            
            # Buscar patrón "Fecha: Día DD de MES YYYY"
            date_pattern = r'Fecha:\s*(?:\w+\s+)?(\d{1,2})\s+de\s+(\w+)\s+(\d{4})'
            date_match = re.search(date_pattern, description, re.IGNORECASE)
            
            if date_match:
                day, month_name, year = date_match.groups()
                month_num = meses_es.get(month_name.lower())
                
                if month_num:
                    try:
                        # Crear fecha del evento
                        event_date = datetime(int(year), month_num, int(day))
                        
                        # Buscar horario si está disponible
                        time_pattern = r'Horario:\s*(\d{1,2}):(\d{2})\s*horas?'
                        time_match = re.search(time_pattern, description, re.IGNORECASE)
                        
                        if time_match:
                            hour, minute = time_match.groups()
                            start_date = event_date.replace(hour=int(hour), minute=int(minute), tzinfo=timezone.utc)
                            # Evento de 3 horas por defecto si no se especifica fin
                            end_date = start_date + timezone.timedelta(hours=3)
                            logger.info(f"📅 Fecha extraída de descripción: {start_date} (con horario)")
                        else:
                            # Sin horario específico: todo el día
                            start_date = event_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                            end_date = event_date.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
                            logger.info(f"📅 Fecha extraída de descripción: {event_date.date()} (día completo)")
                        
                    except ValueError as e:
                        logger.warning(f"⚠️ Error creando fecha desde descripción: {e}")
                else:
                    logger.warning(f"⚠️ Mes no reconocido en descripción: {month_name}")
            else:
                logger.warning(f"⚠️ No se encontró patrón de fecha en descripción")
        
        # 2️⃣ FALLBACK: Usar fechas de órdenes si no se pudo extraer de la descripción
        if not start_date or not end_date:
            orders = woo_data.get('orders', [])
            if orders:
                # Encontrar la orden más antigua y más reciente
                order_dates = []
                for order in orders:
                    if order.get('order_date'):
                        try:
                            if isinstance(order['order_date'], str):
                                order_date = datetime.fromisoformat(order['order_date'].replace('Z', '+00:00'))
                            else:
                                order_date = order['order_date']
                            order_dates.append(order_date)
                        except:
                            continue
                
                if order_dates:
                    earliest_order = min(order_dates)
                    latest_order = max(order_dates)
                    
                    # 🔧 FECHAS ROBUSTAS: Si solo hay una fecha, crear rango de 24 horas
                    if earliest_order.date() == latest_order.date():
                        # Mismo día: 00:00 - 23:59
                        start_date = earliest_order.replace(hour=0, minute=0, second=0, microsecond=0)
                        end_date = earliest_order.replace(hour=23, minute=59, second=59, microsecond=999999)
                        logger.info(f"📅 Fallback - Fecha única de órdenes: {earliest_order.date()} -> Rango completo del día")
                    else:
                        # Múltiples días: desde el primer día hasta el último + 1 día
                        start_date = earliest_order.replace(hour=0, minute=0, second=0, microsecond=0)
                        end_date = latest_order.replace(hour=23, minute=59, second=59, microsecond=999999)
                        logger.info(f"📅 Fallback - Rango de fechas de órdenes: {start_date.date()} - {end_date.date()}")
                else:
                    # Fallback a fechas de migración
                    start_date = migration_request.event_start_date or timezone.now()
                    end_date = migration_request.event_end_date or (start_date + timezone.timedelta(hours=23, minutes=59))
                    logger.warning(f"⚠️ No se encontraron fechas válidas en órdenes, usando fallback final")
            else:
                start_date = migration_request.event_start_date or timezone.now()
                end_date = migration_request.event_end_date or (start_date + timezone.timedelta(hours=23, minutes=59))
                logger.warning(f"⚠️ No hay órdenes, usando fechas por defecto")
        
        return {
            'title': migration_request.event_name,
            'description': migration_request.event_description or product_info.get('product_description', ''),
            'short_description': product_info.get('product_name', '')[:255],
            'status': 'published',  # ✅ Publicado pero no listado
            'visibility': 'unlisted',  # ✅ NO LISTADO - accesible por link pero no comprable
            'type': 'other',  # Tipo genérico
            'template': 'standard',
            'pricing_mode': 'complex',  # Eventos con tickets pagados
            'start_date': start_date,  # ✅ Fecha basada en órdenes reales
            'end_date': end_date,      # ✅ Fecha basada en órdenes reales
            'max_tickets_per_purchase': 10,
            # Ubicación se manejará por separado si se proporciona
            'tags': f'migrado-woocommerce,producto-{product_info["product_id"]}',
        }
    
    def map_order_data(self, woo_order: Dict[str, Any], django_event_id: int, 
                      service_fee_percentage: Decimal) -> Dict[str, Any]:
        """
        Mapea una orden de WooCommerce a una orden Django
        
        Args:
            woo_order: Datos de orden WooCommerce
            django_event_id: ID del evento Django creado
            service_fee_percentage: Porcentaje de cargo por servicio
            
        Returns:
            Dict con datos mapeados para crear orden Django
        """
        # Calcular división de totales
        total = Decimal(str(woo_order.get('order_total', 0)))
        service_fee, organizer_amount = self._calculate_fee_split(total, service_fee_percentage)
        
        # Mapear estado de orden
        woo_status = woo_order.get('order_status', 'pending')
        django_status = self._map_order_status(woo_status)
        
        # ✅ CRÍTICO: Preservar fecha original de WooCommerce
        order_date = woo_order.get('order_date')
        if isinstance(order_date, str):
            try:
                # Convertir string a datetime con timezone
                parsed_date = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
                if parsed_date.tzinfo is None:
                    parsed_date = timezone.make_aware(parsed_date)
                order_date = parsed_date
            except:
                order_date = timezone.now()
        elif not order_date:
            order_date = timezone.now()
        
        return {
            'event': django_event_id,
            'status': django_status,
            'email': woo_order.get('billing_email', ''),
            'first_name': woo_order.get('billing_first_name', ''),
            'last_name': woo_order.get('billing_last_name', ''),
            'phone': woo_order.get('billing_phone', ''),
            'subtotal': organizer_amount,
            'taxes': Decimal(str(woo_order.get('order_tax', 0))),
            'service_fee': service_fee,
            'total': total,
            'currency': woo_order.get('order_currency', self.config.default_currency),
            'payment_method': woo_order.get('payment_method', ''),
            'payment_id': str(woo_order.get('order_id', '')),
            'notes': f'Migrado de WooCommerce - Orden #{woo_order.get("order_id")}',
            
            # ✅ FECHA ORIGINAL DE WOOCOMMERCE
            'order_date': order_date,
            # Metadatos adicionales
            'metadata': {
                'woocommerce_order_id': woo_order.get('order_id'),
                'woocommerce_order_key': woo_order.get('order_key'),
                'original_payment_method': woo_order.get('payment_method_title'),
                'migration_date': datetime.now().isoformat(),
                'billing_address': {
                    'address_1': woo_order.get('billing_address_1'),
                    'city': woo_order.get('billing_city'),
                    'state': woo_order.get('billing_state'),
                    'country': woo_order.get('billing_country'),
                    'postcode': woo_order.get('billing_postcode'),
                }
            }
        }
    
    def map_ticket_data(self, woo_ticket: Dict[str, Any], django_order_item_id: int) -> Dict[str, Any]:
        """
        Mapea un ticket de WooCommerce a un ticket Django
        
        Args:
            woo_ticket: Datos de ticket WooCommerce
            django_order_item_id: ID del OrderItem Django
            
        Returns:
            Dict con datos mapeados para crear ticket Django
        """
        # ✅ CRÍTICO: Preservar fecha original de creación del ticket
        ticket_created = woo_ticket.get('ticket_created')
        if isinstance(ticket_created, str):
            try:
                # Convertir string a datetime con timezone
                parsed_date = datetime.fromisoformat(ticket_created.replace('Z', '+00:00'))
                if parsed_date.tzinfo is None:
                    parsed_date = timezone.make_aware(parsed_date)
                ticket_created = parsed_date
            except:
                ticket_created = timezone.now()
        elif not ticket_created:
            ticket_created = timezone.now()
        
        return {
            'order_item': django_order_item_id,
            'first_name': woo_ticket.get('attendee_first_name', ''),
            'last_name': woo_ticket.get('attendee_last_name', ''),
            'email': woo_ticket.get('attendee_email', ''),
            'status': 'active',
            'check_in_status': 'pending',
            
            # ✅ FECHA ORIGINAL DE WOOCOMMERCE
            'ticket_created': ticket_created,
            
            # Campos personalizados se almacenan en form_data
            'form_data': woo_ticket.get('custom_attendee_fields', {}),
            'metadata': {
                'woocommerce_ticket_id': woo_ticket.get('ticket_id'),
                'woocommerce_post_id': woo_ticket.get('ticket_post_id'),
                'migration_date': datetime.now().isoformat(),
                'purchaser_info': {
                    'first_name': woo_ticket.get('purchaser_first_name'),
                    'last_name': woo_ticket.get('purchaser_last_name'),
                    'email': woo_ticket.get('purchaser_email'),
                }
            }
        }
    
    def create_form_from_custom_fields(self, custom_fields_sample: Dict[str, Any], 
                                     event_name: str) -> Dict[str, Any]:
        """
        Crea un formulario Django basado en los campos personalizados de WooCommerce
        
        Args:
            custom_fields_sample: Muestra de campos personalizados
            event_name: Nombre del evento para el formulario
            
        Returns:
            Dict con datos para crear formulario Django
        """
        if not custom_fields_sample:
            return None
        
        form_fields = []
        for i, (field_name, sample_value) in enumerate(custom_fields_sample.items()):
            # Inferir tipo de campo basado en el valor
            field_type = self._infer_field_type(sample_value)
            
            form_fields.append({
                'label': field_name,
                'name': field_name.lower().replace(' ', '_').replace('ó', 'o').replace('í', 'i'),
                'type': field_type,
                'required': True,  # Asumir que todos son requeridos
                'placeholder': f'Ingresa tu {field_name.lower()}',
                'help_text': f'Campo migrado desde WooCommerce: {field_name}',
                'order': i,
                'width': 'full',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
            })
        
        return {
            'name': f'Formulario {event_name} (Migrado)',
            'description': f'Formulario generado automáticamente desde WooCommerce para {event_name}',
            'fields': form_fields
        }
    
    def _calculate_fee_split(self, total: Decimal, service_fee_percentage: Decimal) -> Tuple[Decimal, Decimal]:
        """
        Calcula la división entre cargo por servicio y monto del organizador
        
        Args:
            total: Monto total de la orden
            service_fee_percentage: Porcentaje de cargo por servicio
            
        Returns:
            Tuple (service_fee, organizer_amount)
        """
        if total <= 0:
            return Decimal('0'), Decimal('0')
        
        # Calcular cargo por servicio
        service_fee = (total * service_fee_percentage / Decimal('100')).quantize(
            Decimal('1'), rounding=ROUND_UP
        )
        
        # El resto va al organizador
        organizer_amount = total - service_fee
        
        # Asegurar que los montos sean enteros y sumen correctamente
        if organizer_amount < 0:
            organizer_amount = Decimal('0')
            service_fee = total
        
        # Verificar que sumen correctamente
        if service_fee + organizer_amount != total:
            # Ajustar el cargo por servicio para que sume exacto
            service_fee = total - organizer_amount
        
        return service_fee, organizer_amount
    
    def _map_order_status(self, woo_status: str) -> str:
        """Mapea estados de orden de WooCommerce a Django"""
        status_mapping = {
            'wc-pending': 'pending',
            'wc-processing': 'paid',
            'wc-on-hold': 'pending',
            'wc-completed': 'paid',
            'wc-cancelled': 'cancelled',
            'wc-refunded': 'refunded',
            'wc-failed': 'failed',
            'pending': 'pending',
            'processing': 'paid',
            'completed': 'paid',
            'cancelled': 'cancelled',
            'refunded': 'refunded',
            'failed': 'failed',
        }
        return status_mapping.get(woo_status, 'pending')
    
    def _infer_field_type(self, sample_value: str) -> str:
        """Infiere el tipo de campo basado en el valor de muestra"""
        if not sample_value:
            return 'text'
        
        sample_lower = str(sample_value).lower()
        
        # Detectar email
        if '@' in sample_lower and '.' in sample_lower:
            return 'email'
        
        # Detectar número
        try:
            float(sample_value)
            return 'number'
        except (ValueError, TypeError):
            pass
        
        # Detectar fecha (formato básico)
        if any(char in sample_value for char in ['/', '-']) and len(sample_value) >= 8:
            try:
                # Intentar parsear como fecha
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y']:
                    try:
                        datetime.strptime(sample_value, fmt)
                        return 'date' if fmt != '%Y' else 'number'
                    except ValueError:
                        continue
            except:
                pass
        
        # Detectar URL
        if sample_lower.startswith(('http://', 'https://', 'www.')):
            return 'url'
        
        # Por defecto, texto
        return 'text'


class DjangoORMClient:
    """Cliente para interactuar directamente con Django ORM (más eficiente que API REST)"""
    
    def __init__(self, config: IntegrationConfig):
        self.config = config
        # No necesitamos session HTTP ya que usamos ORM directo
    
    @transaction.atomic
    def get_or_create_organizer(self, email: str, name: str = "") -> Dict[str, Any]:
        """
        Obtiene un organizador existente o lo crea de forma ENTERPRISE ROBUSTA
        Incluye creación automática de usuario y vinculación completa
        """
        # Validaciones de entrada
        if not email or '@' not in email:
            raise ValueError(f"Email de organizador inválido: {email}")
        
        # 1. Buscar organizador existente por contact_email
        try:
            organizer = Organizer.objects.filter(contact_email=email).first()
            if organizer:
                logger.info(f"✅ Organizador encontrado: {email} (ID: {organizer.id})")
                
                # Verificar que tenga usuario vinculado
                self._ensure_organizer_user_exists(organizer)
                
                return {
                    'id': str(organizer.id),
                    'name': organizer.name,
                    'slug': organizer.slug,
                    'contact_email': organizer.contact_email,
                    'status': organizer.status
                }
        except Exception as e:
            logger.warning(f"⚠️ Error buscando organizador: {e}")
        
        # 2. Crear nuevo organizador con usuario completo
        logger.info(f"🏢 Creando nuevo organizador ENTERPRISE: {email}")
        
        # Generar nombre si no se proporciona
        organizer_name = name or f"Organizador {email.split('@')[0].title()}"
        slug_base = email.split('@')[0].lower().replace('.', '-').replace('_', '-')
        
        # Generar slug único
        base_slug = f"{slug_base}-migrado"
        slug = base_slug
        counter = 1
        while Organizer.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        try:
            # Crear organizador
            organizer = Organizer.objects.create(
                name=organizer_name,
                slug=slug,
                contact_email=email,
                description=f'Organizador migrado desde WooCommerce - {email}',
                status='active',
                onboarding_completed=True,
                is_temporary=False,
                email_validated=True,
                website='',
                contact_phone='',
                address='',
                city='',
                country='CL'
            )
            
            # Crear usuario y vinculación automáticamente
            user, user_created = self._get_or_create_user_for_organizer(email, organizer_name)
            organizer_user = self._create_organizer_user_link(user, organizer)
            
            logger.info(f"✅ Organizador creado exitosamente:")
            logger.info(f"   - Organizador: {organizer.name} (ID: {organizer.id})")
            logger.info(f"   - Usuario: {user.email} ({'creado' if user_created else 'existente'})")
            logger.info(f"   - Vinculación: {organizer_user.id}")
            logger.info(f"   - Permisos: Administrador completo")
            
            return {
                'id': str(organizer.id),
                'name': organizer.name,
                'slug': organizer.slug,
                'contact_email': organizer.contact_email,
                'status': organizer.status,
                'user_created': user_created,
                'user_email': user.email
            }
            
        except Exception as e:
            logger.error(f"❌ Error creando organizador: {e}")
            raise
    
    def _get_or_create_user_for_organizer(self, email: str, name: str) -> Tuple[User, bool]:
        """Crea o obtiene usuario para el organizador"""
        try:
            user = User.objects.get(email=email)
            logger.info(f"👤 Usuario existente encontrado: {email}")
            return user, False
        except User.DoesNotExist:
            logger.info(f"👤 Creando nuevo usuario: {email}")
            
            # Generar contraseña segura temporal
            password = self._generate_secure_password()
            
            # Extraer nombre y apellido
            name_parts = name.split() if name else ['Usuario', 'Migrado']
            first_name = name_parts[0] if len(name_parts) > 0 else 'Usuario'
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else 'Migrado'
            
            # Generar username único basado en email
            username_base = email.split('@')[0]
            username = username_base
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{username_base}{counter}"
                counter += 1
            
            user = User.objects.create_user(
                username=username,  # 👈 REQUERIDO por el modelo personalizado
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
                is_staff=False,  # No es staff del sistema, solo organizador
                is_organizer=True  # 👈 Marcar como organizador
            )
            
            logger.info(f"✅ Usuario creado: {email} (username: {username})")
            logger.info(f"🔑 Contraseña temporal generada (debe cambiarse)")
            
            return user, True
    
    def _create_organizer_user_link(self, user: User, organizer: Organizer) -> OrganizerUser:
        """Crea la vinculación usuario-organizador con permisos completos"""
        # Verificar si ya existe la vinculación
        existing = OrganizerUser.objects.filter(user=user, organizer=organizer).first()
        if existing:
            logger.info(f"🔗 Vinculación ya existe: {user.email} -> {organizer.name}")
            return existing
        
        organizer_user = OrganizerUser.objects.create(
            user=user,
            organizer=organizer,
            is_admin=True,                    # Administrador completo
            can_manage_events=True,           # Puede manejar eventos
            can_manage_accommodations=True,   # Puede manejar alojamientos
            can_manage_experiences=True,      # Puede manejar experiencias
            can_view_reports=True,            # Puede ver reportes
            can_manage_settings=True          # Puede manejar configuraciones
        )
        
        logger.info(f"🔗 Vinculación creada: {user.email} -> {organizer.name}")
        return organizer_user
    
    def _ensure_organizer_user_exists(self, organizer: Organizer):
        """Asegura que el organizador tenga un usuario vinculado"""
        try:
            user = User.objects.get(email=organizer.contact_email)
            organizer_user = OrganizerUser.objects.filter(user=user, organizer=organizer).first()
            
            if not organizer_user:
                logger.info(f"🔗 Creando vinculación faltante para {organizer.contact_email}")
                self._create_organizer_user_link(user, organizer)
                
        except User.DoesNotExist:
            logger.warning(f"⚠️ Usuario no existe para organizador {organizer.contact_email}")
            # Crear usuario para organizador existente
            user, _ = self._get_or_create_user_for_organizer(organizer.contact_email, organizer.name)
            self._create_organizer_user_link(user, organizer)
    
    def _generate_secure_password(self, length: int = 12) -> str:
        """Genera una contraseña segura temporal"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        return password
    
    # Método create_organizer removido - ahora se maneja en get_or_create_organizer
    
    def get_or_create_event(self, event_data: Dict[str, Any], organizer_id: str, 
                           event_name: str) -> Tuple[Dict[str, Any], bool]:
        """
        Obtiene un evento existente o lo crea usando Django ORM
        
        Returns:
            Tuple (event_dict, created_flag)
        """
        # 1. Buscar evento existente por título y organizador
        try:
            event = Event.objects.filter(
                title=event_name,
                organizer_id=organizer_id
            ).first()
            
            if event:
                logger.info(f"Evento encontrado: {event_name} (ID: {event.id})")
                return {
                    'id': str(event.id),
                    'title': event.title,
                    'description': event.description,
                    'organizer': str(event.organizer_id),
                    'status': event.status
                }, False
        except Exception as e:
            logger.warning(f"Error buscando evento: {e}")
        
        # 2. Crear nuevo evento
        logger.info(f"Creando nuevo evento: {event_name}")
        
        # Generar slug único
        base_slug = slugify(event_name)
        slug = base_slug
        counter = 1
        while Event.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        try:
            event = Event.objects.create(
                title=event_name,
                slug=slug,
                description=event_data.get('description', ''),
                short_description=event_data.get('short_description', event_name[:255]),
                organizer_id=organizer_id,
                status='published',  # ✅ Publicado pero no listado
                type='other',  # Por defecto 'other'
                visibility='unlisted',  # ✅ NO LISTADO - accesible por link pero no comprable
                pricing_mode='complex',  # Modo complejo para eventos con tickets
                start_date=event_data.get('start_date', timezone.now()),  # ✅ Usar fecha original
                end_date=event_data.get('end_date', timezone.now() + timezone.timedelta(hours=2)),  # ✅ Usar fecha original
                max_tickets_per_purchase=10,  # Valor por defecto
            )
            
            logger.info(f"Evento creado: {event_name} - ID: {event.id}")
            return {
                'id': str(event.id),
                'title': event.title,
                'description': event.description,
                'organizer': str(event.organizer_id),
                'status': event.status
            }, True
        except Exception as e:
            logger.error(f"Error creando evento: {e}")
            raise
    
    def get_or_create_form(self, form_data: Dict[str, Any], organizer_id: str, 
                          form_name: str) -> Tuple[Dict[str, Any], bool]:
        """
        Obtiene un formulario existente o lo crea usando Django ORM
        
        Returns:
            Tuple (form_dict, created_flag)
        """
        # 1. Buscar formulario existente por nombre y organizador
        try:
            form = Form.objects.filter(
                name=form_name,
                organizer_id=organizer_id
            ).first()
            
            if form:
                logger.info(f"Formulario encontrado: {form_name} (ID: {form.id})")
                return {
                    'id': str(form.id),
                    'name': form.name,
                    'organizer': str(form.organizer_id),
                    'status': form.status
                }, False
        except Exception as e:
            logger.warning(f"Error buscando formulario: {e}")
        
        # 2. Crear nuevo formulario
        logger.info(f"Creando nuevo formulario: {form_name}")
        
        try:
            form = Form.objects.create(
                name=form_name,
                organizer_id=organizer_id,
                description=form_data.get('description', f'Formulario migrado desde WooCommerce - {form_name}'),
                status='active'
            )
            
            # Crear campos del formulario
            for field_data in form_data.get('fields', []):
                form_field = FormField.objects.create(
                    form=form,
                    label=field_data['label'],
                    type=field_data['type'],
                    required=field_data.get('required', False),
                    order=field_data.get('order', 0),
                    placeholder=field_data.get('placeholder', ''),
                    help_text=field_data.get('help_text', ''),
                    default_value=field_data.get('default_value', '')
                )
                
                # Crear opciones para campos select, radio, checkbox
                options = field_data.get('options', {})
                if options and field_data['type'] in ['select', 'radio', 'checkbox', 'multi_select']:
                    for order, (value, label) in enumerate(options.items()):
                        FieldOption.objects.create(
                            field=form_field,
                            label=label,
                            value=value,
                            order=order
                        )
            
            logger.info(f"Formulario creado: {form_name} - ID: {form.id} con {len(form_data.get('fields', []))} campos")
            return {
                'id': str(form.id),
                'name': form.name,
                'organizer': str(form.organizer_id),
                'status': form.status
            }, True
        except Exception as e:
            logger.error(f"Error creando formulario: {e}")
            raise
    
    # Método create_form removido - ahora se maneja en get_or_create_form
    
    # Método create_event removido - ahora se maneja en get_or_create_event
    
    def update_event(self, event_id: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Actualiza un evento existente usando Django ORM"""
        try:
            event = Event.objects.get(id=event_id)
            
            # Actualizar campos permitidos
            if 'title' in event_data:
                event.title = event_data['title']
            if 'description' in event_data:
                event.description = event_data['description']
            if 'status' in event_data:
                event.status = event_data['status']
            if 'max_attendees' in event_data:
                event.max_attendees = event_data['max_attendees']
            
            # 🔧 ARREGLAR VISIBILIDAD: Siempre mantener como unlisted
            if 'visibility' in event_data:
                event.visibility = event_data['visibility']
                logger.info(f"   - Visibilidad actualizada: {event_data['visibility']}")
            
            # 🔧 ARREGLAR FECHAS: Actualizar con fechas reales de WooCommerce
            if 'start_date' in event_data:
                event.start_date = event_data['start_date']
                logger.info(f"   - Fecha inicio actualizada: {event_data['start_date']}")
            if 'end_date' in event_data:
                event.end_date = event_data['end_date']
                logger.info(f"   - Fecha fin actualizada: {event_data['end_date']}")
            
            event.save()
            
            logger.info(f"Evento actualizado: {event.title} - ID: {event.id}")
            logger.info(f"   - Visibilidad: {event.visibility}")
            logger.info(f"   - Fechas: {event.start_date} - {event.end_date}")
            
            return {
                'id': str(event.id),
                'title': event.title,
                'description': event.description,
                'organizer': str(event.organizer_id),
                'status': event.status,
                'visibility': event.visibility,
                'start_date': event.start_date,
                'end_date': event.end_date
            }
        except Event.DoesNotExist:
            logger.error(f"Evento no encontrado: {event_id}")
            raise
        except Exception as e:
            logger.error(f"Error actualizando evento: {e}")
            raise
    
    def get_or_create_order(self, order_data: Dict[str, Any], 
                           woo_order_id: int) -> Tuple[Dict[str, Any], bool]:
        """
        Obtiene una orden existente o la crea basándose en el ID de WooCommerce usando Django ORM
        
        Returns:
            Tuple (order_dict, created_flag)
        """
        # 1. Buscar orden existente por payment_id para SOBRESCRIBIRLA
        existing_order = None
        try:
            existing_order = Order.objects.filter(payment_id=str(woo_order_id)).first()
            if existing_order:
                logger.info(f"🔄 Orden existente encontrada: WooCommerce #{woo_order_id} -> Django #{existing_order.id}")
                logger.info(f"   ✅ SOBRESCRIBIENDO con datos más recientes de WooCommerce...")
                
                # ELIMINAR la orden existente y todos sus datos relacionados
                # Esto eliminará automáticamente OrderItems y Tickets por CASCADE
                existing_order.delete()
                logger.info(f"   🗑️ Orden anterior eliminada completamente")
        except Exception as e:
            logger.warning(f"Error buscando/eliminando orden existente: {e}")
        
        # 2. Crear nueva orden (siempre nueva, con datos más recientes)
        logger.info(f"🆕 Creando orden con datos actualizados de WooCommerce #{woo_order_id}")
        
        try:
            # Calcular subtotal (total - service_fee)
            total_amount = Decimal(str(order_data['total']))
            service_fee = Decimal(str(order_data['service_fee']))
            subtotal = total_amount - service_fee
            
            # ✅ Usar fecha original de WooCommerce
            order_date = order_data.get('order_date')
            if isinstance(order_date, str):
                try:
                    order_date = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
                except:
                    order_date = timezone.now()
            elif not order_date:
                order_date = timezone.now()
            
            # ✅ Desactivar auto_now temporalmente para preservar fechas originales
            from django.db import connection
            
            # Crear orden y guardar con SQL directo para evitar problemas con triggers
            order = Order(
                event_id=order_data['event'],
                payment_id=order_data.get('payment_id', str(woo_order_id)),
                status='paid',  # Las órdenes de WooCommerce ya están pagadas
                email=order_data.get('email', ''),
                first_name=order_data.get('first_name', ''),
                last_name=order_data.get('last_name', ''),
                phone=order_data.get('phone', '') or '',  # Asegurar que no sea None
                subtotal=order_data.get('subtotal', subtotal),
                service_fee=service_fee,
                total=total_amount,
                currency=order_data.get('currency', 'CLP'),
                payment_method=order_data.get('payment_method', 'woocommerce'),
                notes=order_data.get('notes', f"Migrado desde WooCommerce - Order ID: {woo_order_id}")
            )
            
            logger.info(f"💾 Guardando orden WooCommerce #{woo_order_id}...")
            order.save()
            logger.info(f"✅ Orden guardada con ID: {order.id}")
            
            # 🔥 FORZAR fechas de WooCommerce con SQL directo (bypass auto_now/auto_now_add)
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE events_order 
                    SET created_at = %s, updated_at = %s 
                    WHERE id = %s
                """, [order_date, order_date, str(order.id)])
                logger.info(f"📅 Fechas forzadas a: {order_date}")
                
                # Verificar que se guardó correctamente
                cursor.execute("SELECT COUNT(*), created_at FROM events_order WHERE id = %s GROUP BY created_at", [str(order.id)])
                result = cursor.fetchone()
                if result:
                    count, saved_date = result
                    logger.info(f"🔍 Verificación SQL directa: {count} orden(es) con fecha {saved_date}")
                    
                    if count == 0:
                        logger.error(f"❌ ORDEN NO EXISTE EN BD después de save()!")
                        raise Exception(f"La orden {order.id} no se guardó correctamente")
                else:
                    logger.error(f"❌ No se pudo verificar la orden {order.id}")
                    raise Exception(f"La orden {order.id} no se guardó correctamente en la base de datos")
            
            logger.info(f"✅ Orden verificada en BD con SQL directo")
            
            was_existing = existing_order is not None
            action = "SOBRESCRITA" if was_existing else "CREADA"
            logger.info(f"✅ Orden {action}: WooCommerce #{woo_order_id} -> Django #{order.id}")
            
            return {
                'id': str(order.id),
                'payment_id': order.payment_id,
                'status': order.status,
                'total': str(order.total),
                'service_fee': str(order.service_fee),
                'subtotal': str(order.subtotal),
                'was_overwritten': was_existing
            }, True  # Siempre True porque siempre creamos nueva
        except Exception as e:
            logger.error(f"Error creando orden: {e}")
            raise
    
    # Método create_order removido - ahora se maneja en get_or_create_order
    
    @transaction.atomic
    def get_or_create_ticket(self, ticket_data: Dict[str, Any], 
                            woo_ticket_id: str, tickets_count_in_order: int = 1) -> Tuple[Dict[str, Any], bool]:
        """
        Obtiene un ticket existente o lo crea basándose en el ID de WooCommerce usando Django ORM
        Implementación robusta con transacciones atómicas y validaciones enterprise
        
        Returns:
            Tuple (ticket_dict, created_flag)
        """
        # Validaciones de entrada
        if not woo_ticket_id:
            raise ValueError("woo_ticket_id es requerido")
        if not ticket_data.get('order'):
            raise ValueError("order ID es requerido en ticket_data")
        
        # 1. Buscar ticket existente por form_data de WooCommerce
        try:
            # Buscar en form_data por woocommerce_ticket_id
            tickets = Ticket.objects.filter(
                form_data__woocommerce_ticket_id=woo_ticket_id
            ).select_related('order_item__order__event')
            
            if tickets.exists():
                ticket = tickets.first()
                logger.info(f"✅ Ticket encontrado: WooCommerce {woo_ticket_id} -> Django #{ticket.id}")
                return {
                    'id': str(ticket.id),
                    'status': ticket.status,
                    'attendee_name': f"{ticket.first_name} {ticket.last_name}",
                    'attendee_email': ticket.email,
                    'form_data': ticket.form_data
                }, False
        except Exception as e:
            logger.warning(f"⚠️ Error buscando ticket: {e}")
        
        # 2. Crear nuevo ticket con implementación robusta
        logger.info(f"🎫 Creando nuevo ticket para WooCommerce {woo_ticket_id}")
        
        try:
            # Validar y obtener la orden Django
            order_id = ticket_data['order']
            logger.info(f"🔍 Buscando orden {order_id} para crear ticket...")
            
            # Verificar primero con SQL directo
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, payment_id, status FROM events_order WHERE id = %s", [str(order_id)])
                sql_result = cursor.fetchone()
                logger.info(f"🔍 SQL directo - Orden {order_id}: {sql_result}")
            
            try:
                # Usar select_for_update(nowait=True) para evitar deadlocks
                order = Order.objects.select_related('event').select_for_update(nowait=True).get(id=order_id)
                logger.info(f"✅ Orden encontrada por ORM: {order.id} (payment_id: {order.payment_id})")
            except Order.DoesNotExist:
                logger.error(f"❌ Orden {order_id} NO encontrada por ORM!")
                logger.error(f"   - SQL directo encontró: {sql_result}")
                raise ValueError(f"Orden {order_id} no encontrada")
            except Exception as e:
                logger.error(f"❌ Error obteniendo orden {order_id}: {e}")
                logger.error(f"   - SQL directo encontró: {sql_result}")
                # Si SQL directo la encuentra pero ORM falla, hacer query sin lock
                logger.warning(f"⚠️ Reintentando sin lock...")
            try:
                order = Order.objects.select_related('event').get(id=order_id)
                logger.info(f"✅ Orden obtenida sin lock: {order.id}")
            except Order.DoesNotExist:
                raise ValueError(f"Orden {order_id} no encontrada")
            
            # Preparar form_data con información de WooCommerce y campos adicionales
            form_data = ticket_data.get('custom_fields', {})
            form_data.update({
                'woocommerce_ticket_id': woo_ticket_id,
                'migration_timestamp': timezone.now().isoformat(),
                'source': 'woocommerce_migration'
            })
            
            # ✅ Crear o obtener TicketTier específico para este evento
            # Usar el nombre personalizado de la configuración
            from apps.sync_woocommerce.models import SyncConfiguration
            from apps.forms.models import Form
            
            sync_config = SyncConfiguration.objects.filter(django_event_id=order.event.id).first()
            ticket_tier_name = sync_config.ticket_tier_name if sync_config else "General"
            
            # Buscar formulario para vincular
            event_form = None
            if sync_config and sync_config.django_form_id:
                try:
                    event_form = Form.objects.get(id=sync_config.django_form_id)
                except Form.DoesNotExist:
                    pass
            
            # Si no hay formulario en config, buscar por organizador
            if not event_form:
                event_form = Form.objects.filter(organizer_id=order.event.organizer_id).first()
            
            # ✅ Calcular precio promedio para el TicketTier (será actualizado más adelante)
            # Por ahora usar un precio base, se actualizará con el promedio real
            base_price = Decimal('10000')  # Precio base temporal
            
            ticket_tier, tier_created = TicketTier.objects.get_or_create(
                event=order.event,
                name=ticket_tier_name,
                defaults={
                    'type': 'Migrado WooCommerce',  # ✅ Tipo personalizado identificable
                    'price': base_price,  # ✅ Precio base (se actualizará con promedio)
                    'capacity': None,  # Capacidad ilimitada
                    'available': None,  # Disponibilidad ilimitada
                    'description': f'Tickets migrados desde WooCommerce para {order.event.title}',
                    'is_public': False,  # ✅ NO público para evitar compras
                    'is_highlighted': False,
                    'order': 0,
                    'currency': 'CLP',
                    'max_per_order': 10,
                    'min_per_order': 1,
                    'form': event_form  # ✅ VINCULAR FORMULARIO AUTOMÁTICAMENTE
                }
            )
            
            # Si el tier ya existía pero no tenía formulario, vincularlo
            if not tier_created and not ticket_tier.form and event_form:
                ticket_tier.form = event_form
                ticket_tier.save()
                logger.info(f"🔗 Formulario vinculado a TicketTier existente: {event_form.name}")
            
            if tier_created:
                logger.info(f"🎟️ TicketTier creado: {ticket_tier_name}")
            
            # ✅ CALCULAR PRECIO POR TICKET: Usar el número de tickets pasado como parámetro
            # Este valor viene del contexto de migración que ya tiene los datos de WooCommerce
            total_tickets_count = max(1, tickets_count_in_order)
            
            logger.info(f"🎫 Tickets en orden {order.payment_id}: {total_tickets_count} (desde contexto de migración)")
            
            # Calcular precio por ticket (usar subtotal de la orden, no el total con service fee)
            price_per_ticket = order.subtotal / max(1, total_tickets_count)
            
            logger.info(f"💰 Calculando precio por ticket:")
            logger.info(f"   - Total orden (subtotal): ${order.subtotal}")
            logger.info(f"   - Tickets en orden: {total_tickets_count}")
            logger.info(f"   - Precio por ticket: ${price_per_ticket}")
            
            # Buscar OrderItem existente o crear uno nuevo
            order_item, item_created = OrderItem.objects.get_or_create(
                order=order,
                ticket_tier=ticket_tier,
                defaults={
                    'quantity': total_tickets_count,  # ✅ Cantidad real de tickets
                    'unit_price': price_per_ticket,   # ✅ Precio calculado por ticket
                    'unit_service_fee': Decimal('0'),
                    'subtotal': order.subtotal,       # ✅ Subtotal completo de la orden
                    'custom_price': None
                }
            )
            
            # Si el OrderItem ya existía, actualizar precios
            if not item_created:
                order_item.quantity = total_tickets_count
                order_item.unit_price = price_per_ticket
                order_item.subtotal = order.subtotal
                order_item.unit_service_fee = Decimal('0')
                order_item.save()
                logger.info(f"🔄 OrderItem actualizado con nuevos precios")
            else:
                logger.info(f"📦 OrderItem creado: {ticket_tier_name}")
            
            # Validar datos del asistente
            first_name = ticket_data.get('attendee_first_name', '').strip()
            last_name = ticket_data.get('attendee_last_name', '').strip()
            email = ticket_data.get('attendee_email', '').strip()
            
            if not first_name and not last_name:
                logger.warning(f"⚠️ Ticket {woo_ticket_id} sin nombre de asistente")
                first_name = "Asistente"
                last_name = "Sin Nombre"
            
            if not email:
                logger.warning(f"⚠️ Ticket {woo_ticket_id} sin email de asistente")
                email = f"sin-email-{woo_ticket_id}@migrado.local"
            
            # ✅ Usar fecha original de creación del ticket del mapeo
            ticket_created = ticket_data.get('ticket_created')
            if not ticket_created:
                # Fallback: extraer de los datos originales
                ticket_created = ticket_data.get('ticket_created')
                if isinstance(ticket_created, str):
                    try:
                        ticket_created = datetime.fromisoformat(ticket_created.replace('Z', '+00:00'))
                        if ticket_created.tzinfo is None:
                            ticket_created = timezone.make_aware(ticket_created)
                    except:
                        ticket_created = timezone.now()
                elif not ticket_created:
                    ticket_created = timezone.now()
            
            # ✅ DESACTIVAR SEÑALES DE EMAIL durante migración
            from django.db import transaction
            from django.conf import settings
            
            # Marcar que estamos en migración para evitar emails
            old_migration_mode = getattr(settings, 'MIGRATION_MODE', False)
            settings.MIGRATION_MODE = True
            
            try:
                # Crear el ticket con los datos del asistente
                ticket = Ticket.objects.create(
                    order_item=order_item,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    status='active',
                    form_data=form_data  # Aquí van los campos adicionales del formulario
                )
                
                # ✅ Actualizar fechas manualmente después de crear
                Ticket.objects.filter(id=ticket.id).update(
                    created_at=ticket_created,
                    updated_at=ticket_created
                )
                
            finally:
                # Restaurar modo original
                settings.MIGRATION_MODE = old_migration_mode
            
            logger.info(f"✅ Ticket creado exitosamente:")
            logger.info(f"   - WooCommerce ID: {woo_ticket_id}")
            logger.info(f"   - Django ID: {ticket.id}")
            logger.info(f"   - Asistente: {ticket.first_name} {ticket.last_name}")
            logger.info(f"   - Email: {ticket.email}")
            logger.info(f"   - Campos adicionales: {len(form_data)} campos")
            
            return {
                'id': str(ticket.id),
                'status': ticket.status,
                'attendee_name': f"{ticket.first_name} {ticket.last_name}",
                'attendee_email': ticket.email,
                'form_data': ticket.form_data,
                'ticket_tier': ticket_tier_name
            }, True
            
        except Exception as e:
            logger.error(f"❌ Error creando ticket {woo_ticket_id}: {e}")
            logger.error(f"   - Datos del ticket: {ticket_data}")
            raise


class EventMigrator:
    """Clase principal para migrar eventos completos de WooCommerce a Django"""
    
    def __init__(self, config: IntegrationConfig):
        self.config = config
        self.mapper = WooCommerceToDjangoMapper(config)
        self.client = DjangoORMClient(config)
    
    def migrate_event(self, woo_data: Dict[str, Any], 
                     migration_request: EventMigrationRequest) -> Dict[str, Any]:
        """
        Migra un evento completo de WooCommerce a Django con soporte para actualizaciones
        
        Args:
            woo_data: Datos extraídos de WooCommerce
            migration_request: Configuración de migración
            
        Returns:
            Dict con resultado de la migración
        """
        logger.info(f"Iniciando migración de evento: {migration_request.event_name}")
        
        try:
            # 1. Crear/obtener organizador
            organizer = self.client.get_or_create_organizer(
                migration_request.organizer_email,
                migration_request.organizer_name
            )
            logger.info(f"Organizador: {organizer.get('contact_email', organizer.get('email'))} (ID: {organizer['id']})")
            
            # 2. Crear/obtener formulario si hay campos personalizados
            form = None
            form_created = False
            tickets_with_custom_fields = [
                t for t in woo_data['tickets'] 
                if t.get('custom_attendee_fields')
            ]
            
            if tickets_with_custom_fields:
                sample_fields = tickets_with_custom_fields[0]['custom_attendee_fields']
                form_data = self.mapper.create_form_from_custom_fields(
                    sample_fields, 
                    migration_request.event_name
                )
                
                if form_data:
                    form_name = form_data['name']
                    form, form_created = self.client.get_or_create_form(
                        form_data, organizer['id'], form_name
                    )
                    action = "creado" if form_created else "encontrado"
                    logger.info(f"Formulario {action}: {form['name']} (ID: {form['id']})")
            
            # 3. Crear/obtener evento
            event_data = self.mapper.map_event_data(woo_data, migration_request)
            event_data['organizer'] = organizer['id']
            
            event, event_created = self.client.get_or_create_event(
                event_data, organizer['id'], migration_request.event_name
            )
            
            # Si el evento ya existe, actualizarlo con nuevos datos
            if not event_created:
                logger.info(f"Actualizando evento existente: {event['title']} (ID: {event['id']})")
                event = self.client.update_event(event['id'], event_data)
            else:
                logger.info(f"Evento creado: {event['title']} (ID: {event['id']})")
            
            # 🚀 BLANQUEO TOTAL: Eliminar todas las órdenes y tickets existentes del evento
            logger.info(f"🚀 INICIANDO BLANQUEO TOTAL para evento {event['id']}")
            self._cleanup_existing_event_data(event['id'])
            logger.info(f"🏁 BLANQUEO TOTAL COMPLETADO para evento {event['id']}")
            
            # 4. Migrar órdenes y tickets con soporte para actualizaciones
            service_fee_percentage = (
                migration_request.service_fee_percentage or 
                self.config.default_service_fee_percentage
            )
            
            migrated_orders = []
            updated_orders = []  # Siempre vacío después del blanqueo total
            migrated_tickets = []
            updated_tickets = []  # Siempre vacío después del blanqueo total
            
            # 🚀 OPTIMIZACIÓN BULK: Procesar órdenes y tickets en batch
            logger.info(f"🚀 Procesando {len(woo_data['orders'])} órdenes en modo BULK...")
            
            # Paso 1: Preparar datos de todas las órdenes
            orders_to_create = []
            order_mapping = {}  # woo_order_id -> django_order
            
            for woo_order in woo_data['orders']:
                order_data = self.mapper.map_order_data(
                    woo_order, 
                    event['id'], 
                    service_fee_percentage
                )
                woo_order_id = woo_order.get('order_id')
                
                # Preparar objeto Order (sin guardar aún)
                order_date = order_data.get('order_date')
                if isinstance(order_date, str):
                    try:
                        order_date = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
                    except:
                        order_date = timezone.now()
                elif not order_date:
                    order_date = timezone.now()
                
                total_amount = Decimal(str(order_data['total']))
                service_fee = Decimal(str(order_data['service_fee']))
                subtotal = total_amount - service_fee
                
                order_obj = Order(
                    event_id=order_data['event'],
                    payment_id=str(woo_order_id),
                    status='paid',
                    email=order_data.get('email', ''),
                    first_name=order_data.get('first_name', ''),
                    last_name=order_data.get('last_name', ''),
                    phone=order_data.get('phone', '') or '',
                    subtotal=subtotal,
                    service_fee=service_fee,
                    total=total_amount,
                    currency=order_data.get('currency', 'CLP'),
                    payment_method=order_data.get('payment_method', 'woocommerce'),
                    notes=order_data.get('notes', f"Migrado desde WooCommerce - Order ID: {woo_order_id}")
                )
                orders_to_create.append((order_obj, woo_order_id, order_date))
            
            # Paso 2: Crear todas las órdenes de una vez
            logger.info(f"💾 Creando {len(orders_to_create)} órdenes en bulk...")
            Order.objects.bulk_create([o[0] for o in orders_to_create])
            
            # Paso 3: Actualizar fechas con SQL directo (bypass auto_now)
            from django.db import connection
            for order_obj, woo_order_id, order_date in orders_to_create:
                # Buscar el ID que Django asignó
                order_obj.refresh_from_db()
                with connection.cursor() as cursor:
                    cursor.execute("""
                        UPDATE events_order 
                        SET created_at = %s, updated_at = %s 
                        WHERE id = %s
                    """, [order_date, order_date, str(order_obj.id)])
                
                order_mapping[woo_order_id] = {
                    'id': str(order_obj.id),
                    'payment_id': order_obj.payment_id,
                    'status': order_obj.status,
                    'total': str(order_obj.total),
                    'subtotal': str(order_obj.subtotal),
                }
                migrated_orders.append(order_mapping[woo_order_id])
            
            logger.info(f"✅ {len(migrated_orders)} órdenes creadas en bulk")
            
            # Paso 4: Pre-cargar TicketTier y Form (solo 2 queries para todo el evento)
            logger.info(f"🎫 Pre-cargando TicketTier y Form del evento...")
            
            # Obtener organizador del evento para el formulario
            event_obj = Event.objects.get(id=event['id'])
            
            ticket_tier, _ = TicketTier.objects.get_or_create(
                   event_id=event['id'],
                   name='General',
                   defaults={
                       'description': 'Entrada general migrada de WooCommerce',
                       'max_quantity': None,
                       'available_from': timezone.now(),
                       'is_active': True,
                       'is_public': True,  # 🚀 ENTERPRISE: Make public so frontend can see it
                       'price': Decimal('0'),  # Se actualizará después
                   }
               )
            
            event_form, _ = Form.objects.get_or_create(
                name='Información de Asistente',
                organizer=event_obj.organizer,
                defaults={
                    'description': 'Formulario migrado de WooCommerce',
                    'status': 'active'
                }
            )
            
            # Vincular formulario al tier si no está vinculado
            if not ticket_tier.form:
                ticket_tier.form = event_form
                ticket_tier.save()
            
            # 🚀 ENTERPRISE: Update ticket tier with correct capacity and availability
            total_tickets_sold = len(woo_data['tickets'])
            ticket_tier.capacity = total_tickets_sold
            ticket_tier.available = 0  # All tickets are sold
            ticket_tier.is_public = True  # Ensure it's visible to frontend
            ticket_tier.save()
            
            logger.info(f"✅ TicketTier y Form pre-cargados")
            
            # Paso 5: Crear OrderItems y Tickets en modo optimizado
            logger.info(f"🎫 Procesando tickets...")
            order_items_cache = {}  # Cache de OrderItems por order_id
            
            for woo_order in woo_data['orders']:
                woo_order_id = woo_order.get('order_id')
                django_order = order_mapping.get(woo_order_id)
                
                if not django_order:
                    continue
                
                order_tickets = [
                    t for t in woo_data['tickets'] 
                    if t.get('order_id') == woo_order_id
                ]
                
                if not order_tickets:
                    continue
                
                tickets_count_in_order = len(order_tickets)
                
                # Obtener Order object y service_fee_percentage
                order = Order.objects.get(id=django_order['id'])
                service_fee_pct = service_fee_percentage / Decimal('100')
                
                # Crear todos los tickets de esta orden (cada uno con su precio)
                for woo_ticket in order_tickets:
                    # 💰 PRECIO DEL TICKET desde WooCommerce (puede venir como price_paid_clean o expr_10)
                    price_raw = woo_ticket.get('price_paid_clean') or woo_ticket.get('expr_10')
                    logger.info(f"🔍 DEBUG Ticket {woo_ticket.get('ticket_id')}: price_raw={price_raw}, price_paid_raw={woo_ticket.get('price_paid_raw')}")
                    
                    if price_raw:
                        ticket_total_price = Decimal(str(price_raw))
                    else:
                        ticket_total_price = Decimal('0')
                    
                    if ticket_total_price > 0:
                        # Calcular service_fee y subtotal del ticket
                        ticket_service_fee = (ticket_total_price * service_fee_pct).quantize(Decimal('0.01'))
                        ticket_subtotal = ticket_total_price - ticket_service_fee
                        logger.info(f"💰 Ticket {woo_ticket.get('ticket_id')}: Total=${ticket_total_price}, Service Fee=${ticket_service_fee}, Subtotal=${ticket_subtotal}")
                    else:
                        # Fallback: dividir el total de la orden
                        ticket_total_price = order.total / max(1, tickets_count_in_order)
                        ticket_service_fee = order.service_fee / max(1, tickets_count_in_order)
                        ticket_subtotal = order.subtotal / max(1, tickets_count_in_order)
                        logger.warning(f"⚠️ Ticket {woo_ticket.get('ticket_id')} sin precio en WooCommerce, usando fallback")
                    
                    # Crear OrderItem POR TICKET (quantity=1, precio específico)
                    order_item = OrderItem.objects.create(
                        order=order,
                        ticket_tier=ticket_tier,
                        quantity=1,  # Un OrderItem por ticket
                        unit_price=ticket_subtotal,  # Precio sin service_fee
                        unit_service_fee=ticket_service_fee,
                        subtotal=ticket_subtotal,
                        custom_price=None
                    )
                    first_name = woo_ticket.get('attendee_first_name', '').strip()
                    last_name = woo_ticket.get('attendee_last_name', '').strip()
                    email = woo_ticket.get('attendee_email', '').strip()
                    
                    if not first_name and not last_name:
                        first_name = "Asistente"
                        last_name = "Sin Nombre"
                    
                    if not email:
                        email = f"sin-email-{woo_ticket.get('ticket_id')}@migrado.local"
                    
                    # Preparar form_data
                    form_data = woo_ticket.get('custom_attendee_fields', {}) or {}
                    
                    # Crear ticket directamente (sin signal de email)
                    from django.conf import settings
                    old_migration_mode = getattr(settings, 'MIGRATION_MODE', False)
                    settings.MIGRATION_MODE = True
                    
                    try:
                        ticket = Ticket.objects.create(
                            order_item=order_item,
                            first_name=first_name,
                            last_name=last_name,
                            email=email,
                            status='active',
                            form_data=form_data
                        )
                        
                        # Actualizar fechas si es necesario
                        ticket_created = woo_ticket.get('ticket_created')
                        if ticket_created:
                            if isinstance(ticket_created, str):
                                try:
                                    ticket_created = datetime.fromisoformat(ticket_created.replace('Z', '+00:00'))
                                    if ticket_created.tzinfo is None:
                                        ticket_created = timezone.make_aware(ticket_created)
                                except:
                                    ticket_created = None
                            
                            if ticket_created:
                                Ticket.objects.filter(id=ticket.id).update(
                                    created_at=ticket_created,
                                    updated_at=ticket_created
                                )
                        
                        migrated_tickets.append({
                            'id': str(ticket.id),
                            'status': ticket.status,
                            'attendee_name': f"{ticket.first_name} {ticket.last_name}",
                            'attendee_email': ticket.email,
                        })
                    finally:
                        settings.MIGRATION_MODE = old_migration_mode
            
            logger.info(f"✅ {len(migrated_tickets)} tickets creados")
            
            # ✅ ACTUALIZAR PRECIO PROMEDIO DEL TICKET TIER
            self._update_ticket_tier_average_price(event['id'])
            
            # Estadísticas finales
            total_orders = len(migrated_orders) + len(updated_orders)
            total_tickets = len(migrated_tickets) + len(updated_tickets)
            
            logger.info(f"Migración completada:")
            logger.info(f"  - Órdenes: {len(migrated_orders)} nuevas, {len(updated_orders)} actualizadas")
            logger.info(f"  - Tickets: {len(migrated_tickets)} nuevos, {len(updated_tickets)} actualizados")
            
            return {
                'success': True,
                'event': event,
                'event_created': event_created,
                'organizer': organizer,
                'form': form,
                'form_created': form_created,
                'orders_count': total_orders,
                'tickets_count': total_tickets,
                'service_fee_percentage': float(service_fee_percentage),
                'summary': {
                    'total_orders': len(woo_data['orders']),
                    'total_tickets': len(woo_data['tickets']),
                    'migrated_orders': len(migrated_orders),
                    'updated_orders': len(updated_orders),
                    'migrated_tickets': len(migrated_tickets),
                    'updated_tickets': len(updated_tickets),
                },
                'details': {
                    'event_action': 'creado' if event_created else 'actualizado',
                    'form_action': 'creado' if form_created else 'encontrado' if form else 'no_requerido',
                    'organizer_action': 'encontrado',  # Siempre existe después de get_or_create
                }
            }
            
        except Exception as e:
            logger.error(f"Error en migración: {e}")
            return {
                'success': False,
                'error': str(e),
                'event_name': migration_request.event_name
            }
    
    def _update_ticket_tier_average_price(self, event_id: str):
        """
        Actualiza el precio del TicketTier con el promedio de los OrderItems
        """
        try:
            from apps.events.models import Event, TicketTier, OrderItem
            from django.db.models import Avg
            
            event = Event.objects.get(id=event_id)
            ticket_tiers = TicketTier.objects.filter(event=event)
            
            for tier in ticket_tiers:
                # Calcular precio promedio de los OrderItems de este TicketTier
                avg_price = OrderItem.objects.filter(
                    ticket_tier=tier,
                    order__event=event
                ).aggregate(avg_price=Avg('unit_price'))['avg_price']
                
                if avg_price:
                    old_price = tier.price
                    tier.price = avg_price
                    tier.save()
                    
                    logger.info(f"💰 TicketTier '{tier.name}' precio actualizado:")
                    logger.info(f"   - Precio anterior: ${old_price}")
                    logger.info(f"   - Precio promedio: ${avg_price}")
                    
        except Exception as e:
            logger.warning(f"⚠️ No se pudo actualizar precio promedio del TicketTier: {e}")
    
    def _cleanup_existing_event_data(self, event_id: str):
        """
        🚀 BLANQUEO TOTAL: Elimina todas las órdenes y tickets existentes del evento
        
        Esta función garantiza que no haya duplicados al sincronizar,
        eliminando completamente todos los datos existentes antes de crear los nuevos.
        """
        try:
            from apps.events.models import Order, Ticket, OrderItem
            from django.db import transaction
            
            logger.info(f"🧹 BLANQUEO TOTAL: Iniciando limpieza del evento {event_id}")
            
            # Contar datos existentes antes de eliminar (fuera de transacción)
            existing_orders = Order.objects.filter(event_id=event_id)
            orders_count = existing_orders.count()
            
            if orders_count == 0:
                logger.info(f"✨ Evento limpio: No hay datos existentes para eliminar")
                return
            
            # Obtener IDs de órdenes para eliminación robusta
            order_ids = list(existing_orders.values_list('id', flat=True))
            tickets_count = Ticket.objects.filter(order_item__order__event_id=event_id).count()
            items_count = OrderItem.objects.filter(order__event_id=event_id).count()
            
            logger.info(f"🗑️ Eliminando datos existentes:")
            logger.info(f"   - Órdenes: {orders_count}")
            logger.info(f"   - Tickets: {tickets_count}")
            logger.info(f"   - Order Items: {items_count}")
            
            # Estrategia 1: Intentar eliminación masiva con transacción
            try:
                with transaction.atomic():
                    deleted_orders = existing_orders.delete()
                    
                logger.info(f"✅ BLANQUEO COMPLETADO (masivo):")
                logger.info(f"   - Eliminados: {deleted_orders[0]} objetos en total")
                logger.info(f"   - Detalles: {deleted_orders[1]}")
                return
                
            except Exception as delete_error:
                logger.warning(f"⚠️ Error en eliminación masiva: {str(delete_error)[:200]}...")
                logger.info(f"🔄 Cambiando a eliminación individual robusta...")
            
            # Estrategia 2: Eliminación individual sin transacción atómica
            deleted_count = 0
            failed_count = 0
            
            for order_id in order_ids:
                try:
                    # Cada eliminación en su propia transacción
                    with transaction.atomic():
                        order = Order.objects.filter(id=order_id).first()
                        if order:
                            order.delete()
                            deleted_count += 1
                except Exception as individual_error:
                    error_msg = str(individual_error)
                    # Todos los errores van a eliminación SQL pura
                    failed_count += 1
                    logger.warning(f"⚠️ Error eliminando orden {order_id}: {str(individual_error)[:100]}...")
            
            logger.info(f"✅ BLANQUEO COMPLETADO (individual):")
            logger.info(f"   - Eliminadas exitosamente: {deleted_count} órdenes")
            if failed_count > 0:
                logger.warning(f"   - Fallos: {failed_count} órdenes no se pudieron eliminar")
            
            # Verificar limpieza final
            remaining_orders = Order.objects.filter(event_id=event_id).count()
            if remaining_orders > 0:
                logger.warning(f"⚠️ Quedan {remaining_orders} órdenes sin eliminar")
                
                # Estrategia 3: ELIMINACIÓN SQL BRUTAL - Bypasea Django completamente
                logger.info(f"🔧 ELIMINACIÓN SQL BRUTAL: Bypasseando Django ORM completamente...")
                try:
                    from django.db import connection
                    with connection.cursor() as cursor:
                        # 🔥 ELIMINACIÓN BRUTAL: Sin triggers, sin vistas, sin Django ORM
                        
                        # 1. Eliminar tickets directamente por SQL
                        cursor.execute("""
                            DELETE FROM events_ticket 
                            WHERE order_item_id IN (
                                SELECT oi.id FROM events_orderitem oi
                                INNER JOIN events_order o ON oi.order_id = o.id
                                WHERE o.event_id = %s
                            )
                        """, [event_id])
                        tickets_deleted = cursor.rowcount
                        
                        # 2. Eliminar order items directamente por SQL
                        cursor.execute("""
                            DELETE FROM events_orderitem 
                            WHERE order_id IN (
                                SELECT id FROM events_order WHERE event_id = %s
                            )
                        """, [event_id])
                        items_deleted = cursor.rowcount
                        
                        # 3. Eliminar órdenes directamente por SQL
                        cursor.execute("""
                            DELETE FROM events_order WHERE event_id = %s
                        """, [event_id])
                        orders_deleted = cursor.rowcount
                        
                        # 4. Si hay órdenes restantes, eliminación por lotes de IDs específicos
                        if orders_deleted == 0 and remaining_orders > 0:
                            logger.info(f"🔥 ELIMINACIÓN POR LOTES DE IDs...")
                            
                            # Obtener IDs específicos que fallaron
                            failed_order_ids = list(Order.objects.filter(event_id=event_id).values_list('id', flat=True))
                            
                            batch_size = 50  # Procesar en lotes pequeños
                            total_deleted = 0
                            
                            for i in range(0, len(failed_order_ids), batch_size):
                                batch_ids = failed_order_ids[i:i+batch_size]
                                id_placeholders = ','.join(['%s'] * len(batch_ids))
                                
                                # Eliminar tickets del lote
                                cursor.execute(f"""
                                    DELETE FROM events_ticket 
                                    WHERE order_item_id IN (
                                        SELECT id FROM events_orderitem 
                                        WHERE order_id IN ({id_placeholders})
                                    )
                                """, batch_ids)
                                
                                # Eliminar order items del lote
                                cursor.execute(f"""
                                    DELETE FROM events_orderitem 
                                    WHERE order_id IN ({id_placeholders})
                                """, batch_ids)
                                
                                # Eliminar órdenes del lote
                                cursor.execute(f"""
                                    DELETE FROM events_order 
                                    WHERE id IN ({id_placeholders})
                                """, batch_ids)
                                
                                batch_deleted = cursor.rowcount
                                total_deleted += batch_deleted
                                logger.info(f"   🔥 Lote {i//batch_size + 1}: {batch_deleted} órdenes eliminadas")
                            
                            orders_deleted = total_deleted
                        
                    logger.info(f"✅ ELIMINACIÓN SQL BRUTAL COMPLETADA:")
                    logger.info(f"   - Tickets eliminados: {tickets_deleted}")
                    logger.info(f"   - Order Items eliminados: {items_deleted}")
                    logger.info(f"   - Órdenes eliminadas: {orders_deleted}")
                    
                    # Verificar limpieza final
                    final_remaining = Order.objects.filter(event_id=event_id).count()
                    if final_remaining == 0:
                        logger.info(f"🎉 EVENTO COMPLETAMENTE LIMPIO CON SQL BRUTAL")
                    else:
                        logger.warning(f"⚠️ Aún quedan {final_remaining} órdenes después de SQL brutal")
                        
                except Exception as sql_error:
                    logger.error(f"❌ Error en eliminación SQL brutal: {sql_error}")
                    logger.info(f"🔄 Continuando sincronización con datos existentes...")
            else:
                logger.info(f"🎉 Evento completamente limpio")
                    
        except Exception as e:
            logger.error(f"❌ Error crítico en blanqueo total del evento {event_id}: {e}")
            # No hacer raise para no bloquear la sincronización
            logger.info(f"🔄 Continuando sincronización sin blanqueo total...")


def migrate_woocommerce_event(woo_data_file: str, migration_request: EventMigrationRequest,
                            config: IntegrationConfig) -> Dict[str, Any]:
    """
    Función principal para migrar un evento desde archivo JSON de WooCommerce
    
    Args:
        woo_data_file: Ruta al archivo JSON con datos extraídos
        migration_request: Configuración de migración
        config: Configuración de integración
        
    Returns:
        Dict con resultado de la migración
    """
    # Cargar datos de WooCommerce
    with open(woo_data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extraer datos del evento
    if 'results' in data and data['results']:
        woo_data = data['results'][0]['event_data']
    else:
        woo_data = data
    
    # Crear migrador y ejecutar
    migrator = EventMigrator(config)
    return migrator.migrate_event(woo_data, migration_request)
