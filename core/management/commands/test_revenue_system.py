"""
🚀 ENTERPRISE: Command para testear el sistema de revenue completo.

Usage:
    python manage.py test_revenue_system [--event-id ID] [--create-test-order]

Este command ejecuta una suite completa de tests para verificar que:
1. Los valores efectivos se calculan correctamente
2. La distribución proporcional funciona
3. Las validaciones detectan errores
4. Los endpoints retornan datos consistentes
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from apps.events.models import Event, Order, OrderItem, TicketTier, Coupon
from core.revenue_system import (
    calculate_effective_values,
    calculate_and_store_effective_values,
    get_event_revenue,
    validate_revenue_calculation
)
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test completo del sistema de revenue enterprise'

    def add_arguments(self, parser):
        parser.add_argument(
            '--event-id',
            type=int,
            help='ID del evento a testear (opcional)'
        )
        parser.add_argument(
            '--create-test-order',
            action='store_true',
            help='Crear una orden de prueba con descuento'
        )
        parser.add_argument(
            '--validate-all-orders',
            action='store_true',
            help='Validar todas las órdenes existentes'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n🚀 TESTING SISTEMA ENTERPRISE DE REVENUE\n'))
        self.stdout.write('=' * 60)
        
        # Test 1: Función core de cálculo
        self.test_calculation_function()
        
        # Test 2: Validación de órdenes existentes
        if options.get('validate_all_orders'):
            self.test_existing_orders()
        
        # Test 3: Test con evento específico
        if options.get('event_id'):
            self.test_event_revenue(options['event_id'])
        
        # Test 4: Crear orden de prueba
        if options.get('create_test_order'):
            self.test_create_order_with_discount()
        
        # Test 5: Validación cruzada
        self.test_cross_validation()
        
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('✅ TESTING COMPLETADO\n'))

    def test_calculation_function(self):
        """Test 1: Función core de cálculo"""
        self.stdout.write('\n📊 Test 1: Función de cálculo core')
        self.stdout.write('-' * 60)
        
        test_cases = [
            {
                'name': 'Sin descuento',
                'subtotal': Decimal('1000'),
                'service_fee': Decimal('150'),
                'discount': Decimal('0'),
                'expected_total': Decimal('1150')
            },
            {
                'name': 'Descuento 20%',
                'subtotal': Decimal('1000'),
                'service_fee': Decimal('150'),
                'discount': Decimal('230'),
                'expected_total': Decimal('920')
            },
            {
                'name': 'Descuento 50%',
                'subtotal': Decimal('2000'),
                'service_fee': Decimal('300'),
                'discount': Decimal('1150'),
                'expected_total': Decimal('1150')
            },
        ]
        
        all_passed = True
        for case in test_cases:
            try:
                subtotal_eff, service_fee_eff, total = calculate_effective_values(
                    case['subtotal'],
                    case['service_fee'],
                    case['discount']
                )
                
                # Validar que suma es correcta
                calculated_total = subtotal_eff + service_fee_eff
                if abs(calculated_total - total) > 1:  # Allow 1 CLP difference
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ❌ {case['name']}: Suma incorrecta "
                            f"({calculated_total} ≠ {total})"
                        )
                    )
                    all_passed = False
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✅ {case['name']}: "
                            f"subtotal_eff={subtotal_eff}, "
                            f"service_fee_eff={service_fee_eff}, "
                            f"total={total}"
                        )
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ❌ {case['name']}: Error - {e}")
                )
                all_passed = False
        
        if all_passed:
            self.stdout.write(self.style.SUCCESS('  ✅ Todos los tests de cálculo pasaron'))
        else:
            self.stdout.write(self.style.ERROR('  ❌ Algunos tests fallaron'))

    def test_existing_orders(self):
        """Test 2: Validar órdenes existentes"""
        self.stdout.write('\n📋 Test 2: Validación de órdenes existentes')
        self.stdout.write('-' * 60)
        
        paid_orders = Order.objects.filter(status='paid')
        total_orders = paid_orders.count()
        
        self.stdout.write(f'  Encontradas {total_orders} órdenes pagadas')
        
        if total_orders == 0:
            self.stdout.write(self.style.WARNING('  ⚠️  No hay órdenes para validar'))
            return
        
        # Validar primeras 10 órdenes
        orders_to_check = paid_orders[:10]
        passed = 0
        failed = 0
        missing_effective = 0
        
        for order in orders_to_check:
            try:
                # Check si tiene valores efectivos
                if order.subtotal_effective is None:
                    missing_effective += 1
                    continue
                
                # Validar suma
                calculated_total = order.subtotal_effective + order.service_fee_effective
                if abs(float(calculated_total) - float(order.total)) > 1:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ❌ Orden {order.order_number}: "
                            f"Suma incorrecta ({calculated_total} ≠ {order.total})"
                        )
                    )
                    failed += 1
                else:
                    passed += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ❌ Orden {order.order_number}: Error - {e}"
                    )
                )
                failed += 1
        
        self.stdout.write(f'\n  Resultados:')
        self.stdout.write(f'    ✅ Válidas: {passed}')
        self.stdout.write(f'    ❌ Inválidas: {failed}')
        self.stdout.write(f'    ⚠️  Sin valores efectivos: {missing_effective}')
        
        if failed == 0 and missing_effective == 0:
            self.stdout.write(self.style.SUCCESS('  ✅ Todas las órdenes validadas correctamente'))

    def test_event_revenue(self, event_id):
        """Test 3: Revenue de evento específico"""
        self.stdout.write(f'\n🎯 Test 3: Revenue del evento {event_id}')
        self.stdout.write('-' * 60)
        
        try:
            event = Event.objects.get(id=event_id)
            self.stdout.write(f'  Evento: {event.title}')
            
            # Obtener revenue
            revenue = get_event_revenue(event, validate=True)
            
            self.stdout.write(f'\n  Métricas:')
            self.stdout.write(f'    Total Revenue: ${revenue["total_revenue"]:,.0f}')
            self.stdout.write(f'    Gross Revenue: ${revenue["gross_revenue"]:,.0f}')
            self.stdout.write(f'    Service Fees: ${revenue["service_fees"]:,.0f}')
            self.stdout.write(f'    Total Tickets: {revenue["total_tickets"]}')
            self.stdout.write(f'    Total Orders: {revenue["total_orders"]}')
            self.stdout.write(f'    Método: {revenue["calculation_method"]}')
            
            # Validar suma
            calculated_total = revenue['gross_revenue'] + revenue['service_fees']
            if abs(calculated_total - revenue['total_revenue']) <= 1:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n  ✅ Validación: Suma correcta '
                        f'({calculated_total} ≈ {revenue["total_revenue"]})'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'\n  ❌ Validación: Suma incorrecta '
                        f'({calculated_total} ≠ {revenue["total_revenue"]})'
                    )
                )
            
            # Mostrar validación detallada
            if 'validation' in revenue:
                validation = revenue['validation']
                self.stdout.write(f'\n  Validación detallada:')
                for check in validation.get('checks', []):
                    self.stdout.write(f'    ✅ {check["name"]}: {check["message"]}')
                for warning in validation.get('warnings', []):
                    self.stdout.write(
                        self.style.WARNING(f'    ⚠️  {warning["name"]}: {warning["message"]}')
                    )
                for error in validation.get('errors', []):
                    self.stdout.write(
                        self.style.ERROR(f'    ❌ {error["name"]}: {error["message"]}')
                    )
                    
        except Event.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Evento {event_id} no encontrado')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Error: {e}')
            )

    def test_create_order_with_discount(self):
        """Test 4: Crear orden de prueba con descuento"""
        self.stdout.write('\n🧪 Test 4: Crear orden de prueba con descuento')
        self.stdout.write('-' * 60)
        
        try:
            # Buscar un evento con tickets disponibles
            event = Event.objects.filter(
                ticket_tiers__available__gt=0
            ).first()
            
            if not event:
                self.stdout.write(
                    self.style.WARNING('  ⚠️  No hay eventos con tickets disponibles')
                )
                return
            
            ticket_tier = event.ticket_tiers.filter(available__gt=0).first()
            
            self.stdout.write(f'  Evento: {event.title}')
            self.stdout.write(f'  Ticket: {ticket_tier.name} (${ticket_tier.price})')
            
            # Crear orden de prueba
            with transaction.atomic():
                order = Order.objects.create(
                    event=event,
                    email='test@example.com',
                    first_name='Test',
                    last_name='User',
                    subtotal=Decimal('1000'),
                    service_fee=Decimal('150'),
                    discount=Decimal('230'),
                    total=Decimal('920'),
                    status='paid',
                    currency='CLP'
                )
                
                # Crear item
                OrderItem.objects.create(
                    order=order,
                    ticket_tier=ticket_tier,
                    quantity=1,
                    unit_price=Decimal('1000'),
                    unit_service_fee=Decimal('150'),
                    subtotal=Decimal('1150')
                )
                
                # Calcular valores efectivos
                self.stdout.write('\n  Calculando valores efectivos...')
                try:
                    summary = calculate_and_store_effective_values(order)
                    
                    # Refrescar orden
                    order.refresh_from_db()
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ Error calculando valores: {e}')
                    )
                    import traceback
                    self.stdout.write(traceback.format_exc())
                    order.delete()
                    return
                
                self.stdout.write(f'\n  Resultados:')
                self.stdout.write(f'    Subtotal Original: ${order.subtotal}')
                self.stdout.write(f'    Service Fee Original: ${order.service_fee}')
                self.stdout.write(f'    Discount: ${order.discount}')
                self.stdout.write(f'    Total: ${order.total}')
                self.stdout.write(f'    Subtotal Effective: ${order.subtotal_effective}')
                self.stdout.write(f'    Service Fee Effective: ${order.service_fee_effective}')
                
                # Validar
                calculated_total = order.subtotal_effective + order.service_fee_effective
                if abs(float(calculated_total) - float(order.total)) <= 1:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'\n  ✅ Validación: Suma correcta '
                            f'({calculated_total} = {order.total})'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'\n  ❌ Validación: Suma incorrecta '
                            f'({calculated_total} ≠ {order.total})'
                        )
                    )
                
                # Limpiar orden de prueba
                order.delete()
                self.stdout.write('\n  🗑️  Orden de prueba eliminada')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Error: {e}')
            )
            import traceback
            self.stdout.write(traceback.format_exc())

    def test_cross_validation(self):
        """Test 5: Validación cruzada (método 1 vs método 2)"""
        self.stdout.write('\n🔄 Test 5: Validación cruzada')
        self.stdout.write('-' * 60)
        
        # Obtener algunas órdenes pagadas
        orders = Order.objects.filter(status='paid')[:5]
        
        if orders.count() == 0:
            self.stdout.write(
                self.style.WARNING('  ⚠️  No hay órdenes para validar')
            )
            return
        
        self.stdout.write(f'  Validando {orders.count()} órdenes...')
        
        # Método 1: Sumar desde órdenes
        revenue_from_orders = orders.aggregate(
            total=Sum('total'),
            gross=Sum('subtotal_effective'),
            fees=Sum('service_fee_effective')
        )
        
        # Método 2: Sumar desde items
        revenue_from_items = OrderItem.objects.filter(
            order__in=orders
        ).aggregate(
            total=Sum('subtotal_effective')
        )
        
        total_from_orders = float(revenue_from_orders['total'] or 0)
        gross_from_orders = float(revenue_from_orders['gross'] or 0)
        fees_from_orders = float(revenue_from_orders['fees'] or 0)
        total_from_items = float(revenue_from_items['total'] or 0)
        
        self.stdout.write(f'\n  Método 1 (desde órdenes):')
        self.stdout.write(f'    Total: ${total_from_orders:,.0f}')
        self.stdout.write(f'    Gross: ${gross_from_orders:,.0f}')
        self.stdout.write(f'    Fees: ${fees_from_orders:,.0f}')
        
        self.stdout.write(f'\n  Método 2 (desde items):')
        self.stdout.write(f'    Total: ${total_from_items:,.0f}')
        
        # Validar
        diff = abs(total_from_orders - total_from_items)
        if diff <= orders.count():  # Allow 1 CLP per order
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n  ✅ Validación cruzada: Diferencia mínima '
                    f'({diff} CLP, permitido: {orders.count()} CLP)'
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f'\n  ❌ Validación cruzada: Diferencia grande '
                    f'({diff} CLP)'
                )
            )

