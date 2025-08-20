"""
🚀 ENTERPRISE: Setup payment providers command
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from payment_processor.models import PaymentProvider, PaymentMethod


class Command(BaseCommand):
    help = '🚀 Setup payment providers and methods for Tuki platform'

    def handle(self, *args, **options):
        self.stdout.write('🚀 Setting up payment providers...')
        
        # Create Transbank WebPay Plus provider
        webpay_provider, created = PaymentProvider.objects.get_or_create(
            name='Transbank WebPay Plus',
            defaults={
                'provider_type': 'transbank_webpay_plus',
                'is_active': True,
                'is_sandbox': settings.TRANSBANK_WEBPAY_PLUS_SANDBOX,
                'config': {
                    'commerce_code': settings.TRANSBANK_WEBPAY_PLUS_COMMERCE_CODE,
                    'api_key': settings.TRANSBANK_WEBPAY_PLUS_API_KEY,
                },
                'min_amount': 50,  # Minimum 50 CLP
                'max_amount': 10000000,  # Maximum 10M CLP
                'supported_currencies': ['CLP'],
                'priority': 100,
                'timeout_seconds': 30,
                'retry_attempts': 3,
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('✅ Created Transbank WebPay Plus provider'))
        else:
            self.stdout.write('ℹ️ Transbank WebPay Plus provider already exists')
        
        # Create payment methods for WebPay Plus
        methods = [
            {
                'method_type': 'credit_card',
                'display_name': 'Tarjeta de Crédito',
                'description': 'Paga con tu tarjeta de crédito de forma segura',
                'display_order': 1,
            },
            {
                'method_type': 'debit_card', 
                'display_name': 'Tarjeta de Débito',
                'description': 'Paga con tu tarjeta de débito RedCompra',
                'display_order': 2,
            },
        ]
        
        for method_data in methods:
            method, created = PaymentMethod.objects.get_or_create(
                provider=webpay_provider,
                method_type=method_data['method_type'],
                defaults=method_data
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'✅ Created payment method: {method.display_name}'))
        
        # Show summary
        total_providers = PaymentProvider.objects.filter(is_active=True).count()
        total_methods = PaymentMethod.objects.filter(is_active=True).count()
        
        self.stdout.write('')
        self.stdout.write('📊 SUMMARY:')
        self.stdout.write(f'  Active providers: {total_providers}')
        self.stdout.write(f'  Active methods: {total_methods}')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('🎉 Payment system setup completed!'))
