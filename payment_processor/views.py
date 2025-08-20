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
    PaymentProviderSerializer, PaymentMethodSerializer, CreatePaymentSerializer,
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


class PaymentViewSet(viewsets.ModelViewSet):
    """
    🚀 ENTERPRISE: Payment processing endpoints
    """
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get payments for authenticated user's orders"""
        if not self.request.user.is_authenticated:
            return Payment.objects.none()
        
        # Get payments for orders belonging to the user
        return Payment.objects.filter(
            order__user=self.request.user
        ).select_related('payment_method', 'payment_method__provider', 'order')
    
    @action(detail=False, methods=['post'])
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
                
                # Verify user owns the order (security check)
                if order.user != request.user:
                    logger.error(f"🚨 SECURITY: User {request.user.id} tried to pay for order {order.id} owned by {order.user_id}")
                    return Response({
                        'success': False,
                        'error': 'Unauthorized access to order'
                    }, status=status.HTTP_403_FORBIDDEN)
                
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