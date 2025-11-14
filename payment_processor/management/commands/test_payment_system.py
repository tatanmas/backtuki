"""
🚀 ENTERPRISE: Test payment system with Transbank sandbox
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from payment_processor.models import PaymentProvider, PaymentMethod, Payment
from payment_processor.services import PaymentServiceFactory
from apps.events.models import Order, Event
from decimal import Decimal
import json


class Command(BaseCommand):
    help = '🚀 Test payment system with Transbank WebPay Plus sandbox'

    def add_arguments(self, parser):
        parser.add_argument(
            '--order-id',
            type=str,
            help='Order ID to test payment with'
        )
        parser.add_argument(
            '--amount',
            type=float,
            default=1000.0,
            help='Amount to test (default: 1000 CLP)'
        )

    def handle(self, *args, **options):
        self.stdout.write('🚀 Testing Transbank WebPay Plus integration...')
        
        try:
            # Get WebPay Plus provider
            provider = PaymentProvider.objects.get(provider_type='transbank_webpay_plus')
            self.stdout.write(f'✅ Found provider: {provider.name}')
            self.stdout.write(f'   - Sandbox mode: {provider.is_sandbox}')
            self.stdout.write(f'   - Commerce code: {provider.config.get("commerce_code")}')
            
            # Get payment method
            method = PaymentMethod.objects.filter(provider=provider, method_type='credit_card').first()
            if not method:
                self.stdout.write(self.style.ERROR('❌ No credit card payment method found'))
                return
            
            self.stdout.write(f'✅ Found payment method: {method.display_name}')
            
            # Get or create test order
            order_id = options.get('order_id')
            if order_id:
                try:
                    order = Order.objects.get(id=order_id)
                    self.stdout.write(f'✅ Using existing order: {order.id}')
                except Order.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f'❌ Order {order_id} not found'))
                    return
            else:
                # Find a pending order
                order = Order.objects.filter(status='pending').first()
                if not order:
                    self.stdout.write(self.style.ERROR('❌ No pending orders found. Create an order first.'))
                    return
                
                self.stdout.write(f'✅ Using pending order: {order.id}')
            
            self.stdout.write(f'   - Order total: ${order.total}')
            self.stdout.write(f'   - Order status: {order.status}')
            
            # Create payment service
            service = PaymentServiceFactory.create_service(provider)
            self.stdout.write('✅ Created payment service')
            
            # Create payment
            payment = service.create_payment(order, order.total, method)
            self.stdout.write(f'✅ Created payment: {payment.buy_order}')
            
            # Process payment (create transaction with Transbank)
            self.stdout.write('🔄 Processing payment with Transbank...')
            result = service.process_payment(payment)
            
            if result['success']:
                self.stdout.write(self.style.SUCCESS('✅ Payment processed successfully!'))
                self.stdout.write(f'   - Token: {result["token"]}')
                self.stdout.write(f'   - Payment URL: {result["payment_url"]}')
                self.stdout.write('')
                self.stdout.write('🎯 NEXT STEPS:')
                self.stdout.write('1. Open the payment URL in your browser')
                self.stdout.write('2. Use these test cards:')
                self.stdout.write('')
                self.stdout.write('   💳 VISA (Successful):')
                self.stdout.write('      Card: 4051 8856 0000 0005')
                self.stdout.write('      CVV: 123')
                self.stdout.write('      Expiry: Any future date')
                self.stdout.write('')
                self.stdout.write('   💳 MASTERCARD (Successful):')
                self.stdout.write('      Card: 5186 0595 0000 0003')
                self.stdout.write('      CVV: 123')
                self.stdout.write('      Expiry: Any future date')
                self.stdout.write('')
                self.stdout.write('   💳 VISA (Failed):')
                self.stdout.write('      Card: 4051 8842 3993 7763')
                self.stdout.write('      CVV: 123')
                self.stdout.write('      Expiry: Any future date')
                self.stdout.write('')
                self.stdout.write(f'3. After completing payment, the return URL will be:')
                self.stdout.write(f'   {settings.FRONTEND_URL}/payment/return')
                self.stdout.write('')
                self.stdout.write(f'4. Test the return endpoint with:')
                self.stdout.write(f'   curl -X POST "http://localhost:8000/api/v1/payments/webpay_return/" \\')
                self.stdout.write(f'        -H "Content-Type: application/json" \\')
                self.stdout.write(f'        -d \'{{"token_ws": "{result["token"]}"}}\'')
                
            else:
                self.stdout.write(self.style.ERROR('❌ Payment processing failed'))
                self.stdout.write(f'   Error: {result.get("error", "Unknown error")}')
                
                # Show transaction logs
                if payment.transactions.exists():
                    self.stdout.write('')
                    self.stdout.write('📋 Transaction logs:')
                    for tx in payment.transactions.all():
                        status_icon = '✅' if tx.is_successful else '❌'
                        self.stdout.write(f'   {status_icon} {tx.transaction_type}: {tx.error_message or "Success"}')
                        if tx.duration_ms:
                            self.stdout.write(f'      Duration: {tx.duration_ms}ms')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'💥 Error: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
