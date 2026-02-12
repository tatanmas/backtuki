"""
🚀 ENTERPRISE PAYMENT VIEWS
High-performance payment processing endpoints.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
import logging

from .models import Payment, PaymentProvider, PaymentMethod, SavedCard
from .serializers import (
    PaymentProviderSerializer, PaymentProviderAdminSerializer, PaymentMethodSerializer, CreatePaymentSerializer,
    PaymentSerializer, PaymentStatusSerializer, WebPayReturnSerializer,
    SavedCardSerializer, PaymentSummarySerializer
)
from .services import PaymentServiceFactory, PaymentServiceException
from apps.events.models import Order

logger = logging.getLogger(__name__)


class PaymentMethodsPublicView(APIView):
    """
    🚀 ENTERPRISE: Public endpoint for payment methods
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        """Get available payment methods"""
        try:
            # Get active payment methods
            methods = PaymentMethod.objects.filter(
                is_active=True,
                provider__is_active=True
            ).select_related('provider').order_by('display_order')
            
            serializer = PaymentMethodSerializer(methods, many=True)
            
            return Response({
                'success': True,
                'payment_methods': serializer.data,
                'count': methods.count()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"💥 PAYMENT METHODS ERROR: {str(e)}")
            return Response({
                'success': False,
                'error': 'Error retrieving payment methods'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaymentProvidersListView(APIView):
    """
    🚀 ENTERPRISE: Admin endpoint for listing all payment providers
    """
    permission_classes = [permissions.AllowAny]  # For deployment automation
    
    def get(self, request):
        """List all payment providers with admin details"""
        try:
            providers = PaymentProvider.objects.all().order_by('-priority', 'name')
            serializer = PaymentProviderAdminSerializer(providers, many=True)
            
            return Response({
                'success': True,
                'providers': serializer.data,
                'count': providers.count()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"💥 PAYMENT PROVIDERS LIST ERROR: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaymentSetupView(APIView):
    """
    🚀 ENTERPRISE: Admin endpoint for payment setup
    """
    permission_classes = [permissions.AllowAny]  # For deployment automation
    
    def post(self, request):
        """Setup payment providers and methods"""
        try:
            from django.core.management import call_command
            from io import StringIO
            
            # Capture command output
            out = StringIO()
            call_command('setup_payment_providers', stdout=out)
            output = out.getvalue()
            
            return Response({
                'success': True,
                'message': 'Payment providers setup completed',
                'output': output
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"💥 PAYMENT SETUP ERROR: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TransbankUpdateView(APIView):
    """
    🚀 ENTERPRISE: Admin endpoint for updating Transbank credentials
    """
    permission_classes = [permissions.AllowAny]  # For deployment automation
    
    def post(self, request):
        """Update Transbank credentials"""
        try:
            commerce_code = request.data.get('commerce_code')
            api_key = request.data.get('api_key')
            is_sandbox = request.data.get('is_sandbox', False)
            
            if not commerce_code or not api_key:
                return Response({
                    'success': False,
                    'error': 'Both commerce_code and api_key are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
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
            logger.info(f"✅ Updated Transbank WebPay Plus provider to {env_mode}")
            
            return Response({
                'success': True,
                'message': f'Transbank credentials updated to {env_mode}',
                'provider': {
                    'id': str(provider.id),
                    'name': provider.name,
                    'is_sandbox': provider.is_sandbox,
                    'commerce_code': commerce_code,
                    'api_key_preview': api_key[:20] + '...' if len(api_key) > 20 else api_key
                }
            }, status=status.HTTP_200_OK)
            
        except PaymentProvider.DoesNotExist:
            # 🚀 ENTERPRISE: Si el provider no existe, crearlo automáticamente
            logger.info("⚠️ Transbank WebPay Plus provider not found, creating it...")
            try:
                provider = PaymentProvider.objects.create(
                    name='Transbank WebPay Plus',
                    provider_type='transbank_webpay_plus',
                    is_active=True,
                    is_sandbox=is_sandbox,
                    config={
                        'commerce_code': commerce_code,
                        'api_key': api_key,
                    },
                    min_amount=50,  # Minimum 50 CLP
                    max_amount=10000000,  # Maximum 10M CLP
                    supported_currencies=['CLP'],
                    priority=100,
                    timeout_seconds=30,
                    retry_attempts=3,
                )
                
                # 🚀 ENTERPRISE: Create payment methods for the provider
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
                    PaymentMethod.objects.get_or_create(
                        provider=provider,
                        method_type=method_data['method_type'],
                        defaults=method_data
                    )
                    logger.info(f"✅ Created payment method: {method_data['display_name']}")
                
                env_mode = "SANDBOX" if is_sandbox else "PRODUCTION"
                logger.info(f"✅ Created and configured Transbank WebPay Plus provider to {env_mode}")
                
                return Response({
                    'success': True,
                    'message': f'Transbank WebPay Plus provider created and configured to {env_mode}',
                    'provider': {
                        'id': str(provider.id),
                        'name': provider.name,
                        'is_sandbox': provider.is_sandbox,
                        'commerce_code': commerce_code,
                        'api_key_preview': api_key[:20] + '...' if len(api_key) > 20 else api_key
                    }
                }, status=status.HTTP_201_CREATED)
            except Exception as create_error:
                logger.error(f"💥 ERROR creating provider: {str(create_error)}")
                return Response({
                    'success': False,
                    'error': f'Failed to create provider: {str(create_error)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except Exception as e:
            logger.error(f"💥 TRANSBANK UPDATE ERROR: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaymentViewSet(viewsets.ModelViewSet):
    """
    🚀 ENTERPRISE: Payment processing endpoints
    """
    serializer_class = PaymentSerializer
    permission_classes = [permissions.AllowAny]  # Public endpoint like booking and payment-methods
    
    def get_queryset(self):
        """Get payments for authenticated user's orders"""
        if not self.request.user.is_authenticated:
            return Payment.objects.none()
        
        # Get payments for orders belonging to the user
        return Payment.objects.filter(
            order__user=self.request.user
        ).select_related('payment_method', 'payment_method__provider', 'order')
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def create_payment(self, request):
        """
        🚀 ENTERPRISE: Create a new payment
        """
        
        serializer = CreatePaymentSerializer(data=request.data)
        
        if not serializer.is_valid():
            logger.warning(f"🚨 PAYMENT: Invalid payment creation data: {serializer.errors}")
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Get validated data
                order = Order.objects.get(id=serializer.validated_data['order_id'])
                payment_method = PaymentMethod.objects.get(id=serializer.validated_data['payment_method_id'])
                
                
                # 🚀 ENTERPRISE: Security check for public endpoint
                # Allow payment if:
                # 1. User is anonymous (order created anonymously and will be linked by email)
                # 2. User is authenticated and owns the order directly  
                # 3. User is authenticated and email matches order email (existing account flow)
                
                if request.user.is_authenticated:
                    user_owns_order = order.user == request.user
                    email_matches = request.user.email.lower() == order.email.lower()
                    
                    # 🚀 ENTERPRISE: Check if user is organizer of the event (event orders only)
                    from apps.organizers.models import OrganizerUser
                    is_event_organizer = False
                    try:
                        if order.event:
                            organizer_user = OrganizerUser.objects.get(user=request.user)
                            is_event_organizer = order.event.organizer == organizer_user.organizer
                            if is_event_organizer:
                                logger.info(f"🎯 ORGANIZER: User {request.user.id} is organizer of event {order.event.id}")
                    except OrganizerUser.DoesNotExist:
                        pass
                    
                    if not (user_owns_order or email_matches or is_event_organizer):
                        logger.error(f"🚨 SECURITY: User {request.user.id} ({request.user.email}) tried to pay for order {order.id} owned by {order.user_id} ({order.email})")
                        return Response({
                            'success': False,
                            'error': 'Unauthorized access to order'
                        }, status=status.HTTP_403_FORBIDDEN)
                else:
                    # Anonymous user - payment allowed (order linking happens during booking)
                    pass
                
                # Log successful authorization
                if request.user.is_authenticated:
                    user_owns_order = order.user == request.user
                    email_matches = request.user.email.lower() == order.email.lower()
                    if user_owns_order:
                        logger.info(f"✅ PAYMENT AUTH: User {request.user.id} owns order {order.id}")
                    elif email_matches:
                        logger.info(f"✅ PAYMENT AUTH: User {request.user.id} authorized by email match for order {order.id}")
                    elif is_event_organizer:
                        logger.info(f"✅ PAYMENT AUTH: User {request.user.id} authorized as event organizer for order {order.id}")
                else:
                    logger.info(f"✅ PAYMENT AUTH: Anonymous user payment for order {order.id}")
                
                # Create payment service
                service = PaymentServiceFactory.create_service(payment_method.provider)
                
                # Create payment record
                payment = service.create_payment(order, order.total, payment_method)
                
                logger.info(f"💳 PAYMENT: Created payment {payment.buy_order} for order {order.id}")
                
                # Process payment with provider
                result = service.process_payment(payment)
                
                if result['success']:
                    logger.info(f"✅ PAYMENT: Successfully processed payment {payment.buy_order}")
                    
                    return Response({
                        'success': True,
                        'payment': PaymentSerializer(payment).data,
                        'payment_url': result.get('payment_url'),
                        'token': result.get('token'),
                        'redirect_required': True,
                        'message': 'Payment created successfully. Redirect user to payment_url.'
                    }, status=status.HTTP_201_CREATED)
                else:
                    logger.error(f"❌ PAYMENT: Failed to process payment {payment.buy_order}: {result.get('error')}")
                    
                    return Response({
                        'success': False,
                        'payment': PaymentSerializer(payment).data,
                        'error': result.get('error', 'Payment processing failed'),
                        'redirect_required': False
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
        except PaymentServiceException as e:
            logger.error(f"💥 PAYMENT SERVICE ERROR: {str(e)}")
            return Response({
                'success': False,
                'error': f'Payment service error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except Exception as e:
            logger.error(f"💥 PAYMENT CREATION ERROR: {str(e)}")
            return Response({
                'success': False,
                'error': 'Internal server error during payment creation'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def webpay_return(self, request):
        """
        🚀 ENTERPRISE: Handle WebPay return after user completes payment
        """
        serializer = WebPayReturnSerializer(data=request.data)
        
        if not serializer.is_valid():
            logger.warning(f"🚨 WEBPAY RETURN: Invalid return data: {serializer.errors}")
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        token = serializer.validated_data['token_ws']
        
        try:
            # Get payment by token
            payment = Payment.objects.select_related('payment_method', 'order').get(token=token)
            
            logger.info(f"🔄 WEBPAY RETURN: Processing return for payment {payment.buy_order}")
            
            # Create payment service
            service = PaymentServiceFactory.create_service(payment.payment_method.provider)
            
            # Confirm payment with Transbank
            result = service.confirm_payment(token)
            
            if result['success']:
                logger.info(f"✅ WEBPAY RETURN: Payment {payment.buy_order} confirmed successfully")
                
                # 🚀 ENTERPRISE FIX: Refresh payment and order from database
                payment.refresh_from_db()
                payment.order.refresh_from_db()
                
                return Response({
                    'success': True,
                    'payment': PaymentSerializer(payment).data,
                    'transaction_data': result.get('transaction_data', {}),
                    'order_status': payment.order.status,
                    'message': 'Payment completed successfully'
                }, status=status.HTTP_200_OK)
            else:
                logger.error(f"❌ WEBPAY RETURN: Payment {payment.buy_order} confirmation failed: {result.get('error')}")
                
                return Response({
                    'success': False,
                    'payment': PaymentSerializer(payment).data,
                    'error': result.get('error', 'Payment confirmation failed'),
                    'message': 'Payment was not successful'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Payment.DoesNotExist:
            logger.error(f"🚨 WEBPAY RETURN: Payment not found for token {token}")
            return Response({
                'success': False,
                'error': 'Payment not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            logger.error(f"💥 WEBPAY RETURN ERROR: {str(e)}")
            return Response({
                'success': False,
                'error': 'Internal server error during payment confirmation'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)