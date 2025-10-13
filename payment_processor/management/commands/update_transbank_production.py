"""
🚀 ENTERPRISE: Update Transbank credentials for production
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from payment_processor.models import PaymentProvider


class Command(BaseCommand):
    help = '🚀 Update Transbank WebPay Plus credentials for production'

    def add_arguments(self, parser):
        parser.add_argument(
            '--commerce-code',
            type=str,
            help='Production commerce code from Transbank'
        )
        parser.add_argument(
            '--api-key',
            type=str,
            help='Production API key from Transbank'
        )
        parser.add_argument(
            '--sandbox',
            action='store_true',
            help='Set to sandbox mode (default: production)'
        )

    def handle(self, *args, **options):
        commerce_code = options.get('commerce_code')
        api_key = options.get('api_key')
        is_sandbox = options.get('sandbox', False)
        
        if not commerce_code or not api_key:
            self.stdout.write(
                self.style.ERROR('❌ Both --commerce-code and --api-key are required')
            )
            return
        
        try:
            # Update existing provider
            provider = PaymentProvider.objects.get(
                provider_type='transbank_webpay_plus',
                name='Transbank WebPay Plus'
            )
            
            # Update configuration
            provider.config = {
                'commerce_code': commerce_code,
                'api_key': api_key,
            }
            provider.is_sandbox = is_sandbox
            provider.save()
            
            env_mode = "SANDBOX" if is_sandbox else "PRODUCTION"
            self.stdout.write(
                self.style.SUCCESS(f'✅ Updated Transbank WebPay Plus provider to {env_mode}')
            )
            self.stdout.write(f'   Commerce Code: {commerce_code}')
            self.stdout.write(f'   API Key: {api_key[:20]}...')
            self.stdout.write(f'   Sandbox Mode: {is_sandbox}')
            
        except PaymentProvider.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('❌ Transbank WebPay Plus provider not found')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error updating provider: {str(e)}')
            )
