"""
🚀 ENTERPRISE PAYMENT SERVICES
High-performance, multi-provider payment processing system.
"""

import requests
import hashlib
import hmac
import json
import time
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from django.conf import settings
from django.utils import timezone
from django.db import transaction, models
from .models import Payment, PaymentProvider, PaymentMethod, PaymentTransaction
import logging

logger = logging.getLogger(__name__)


def finalize_accommodation_payment(payment: Payment) -> None:
    """
    Mark accommodation reservation as paid, update WhatsApp request, and send notifications.
    Used by webhook success path and tests.
    """
    order = payment.order
    if getattr(order, 'order_kind', None) != 'accommodation':
        return
    acc_res = order.accommodation_reservation
    if not acc_res:
        return
    acc_res.status = 'paid'
    acc_res.paid_at = timezone.now()
    acc_res.save(update_fields=['status', 'paid_at'])
    logger.info(f"✅ [PAYMENT] Accommodation reservation {acc_res.reservation_id} marked as paid")

    from apps.whatsapp.models import WhatsAppReservationRequest
    wa_req = WhatsAppReservationRequest.objects.filter(
        linked_accommodation_reservation=acc_res
    ).first()
    if wa_req:
        wa_req.payment_received_at = timezone.now()
        wa_req.save(update_fields=['payment_received_at'])

    try:
        from apps.whatsapp.services.payment_success_notifier import (
            notify_operator_payment_received,
            notify_customer_payment_success,
        )
        notify_operator_payment_received(payment)
        notify_customer_payment_success(payment)
    except Exception:
        logger.exception("WhatsApp accommodation payment notifications failed")


def finalize_car_rental_payment(payment: Payment) -> None:
    """
    Mark car rental reservation as paid, update WhatsApp request, and send notifications.
    """
    order = payment.order
    if getattr(order, 'order_kind', None) != 'car_rental':
        return
    car_res = order.car_rental_reservation
    if not car_res:
        return
    car_res.status = 'paid'
    car_res.paid_at = timezone.now()
    car_res.save(update_fields=['status', 'paid_at'])
    logger.info(f"✅ [PAYMENT] Car rental reservation {car_res.reservation_id} marked as paid")

    from apps.whatsapp.models import WhatsAppReservationRequest
    wa_req = WhatsAppReservationRequest.objects.filter(
        linked_car_rental_reservation=car_res
    ).first()
    if wa_req:
        wa_req.payment_received_at = timezone.now()
        wa_req.save(update_fields=['payment_received_at'])

    try:
        from apps.whatsapp.services.payment_success_notifier import (
            notify_operator_payment_received,
            notify_customer_payment_success,
        )
        notify_operator_payment_received(payment)
        notify_customer_payment_success(payment)
    except Exception:
        logger.exception("WhatsApp car_rental payment notifications failed")


class PaymentServiceException(Exception):
    """Custom exception for payment service errors"""
    pass


class BasePaymentService:
    """
    🚀 ENTERPRISE: Base payment service for all providers
    """
    
    def __init__(self, provider: PaymentProvider):
        self.provider = provider
        self.config = provider.config
        self.is_sandbox = provider.is_sandbox
        self.timeout = provider.timeout_seconds
        self.retry_attempts = provider.retry_attempts
    
    def create_payment(self, order, amount: Decimal, payment_method: PaymentMethod) -> Payment:
        """Create a new payment"""
        raise NotImplementedError("Subclasses must implement create_payment")
    
    def process_payment(self, payment: Payment) -> Dict[str, Any]:
        """Process the payment"""
        raise NotImplementedError("Subclasses must implement process_payment")
    
    def capture_payment(self, payment: Payment) -> Dict[str, Any]:
        """Capture an authorized payment"""
        raise NotImplementedError("Subclasses must implement capture_payment")
    
    def refund_payment(self, payment: Payment, amount: Optional[Decimal] = None) -> Dict[str, Any]:
        """Refund a payment"""
        raise NotImplementedError("Subclasses must implement refund_payment")
    
    def get_payment_status(self, payment: Payment) -> Dict[str, Any]:
        """Get current payment status"""
        raise NotImplementedError("Subclasses must implement get_payment_status")
    
    def log_transaction(self, payment: Payment, transaction_type: str, 
                       request_data: Dict, response_data: Dict, 
                       is_successful: bool, error_message: str = "", 
                       duration_ms: Optional[int] = None):
        """Log transaction for audit and debugging"""
        PaymentTransaction.objects.create(
            payment=payment,
            transaction_type=transaction_type,
            request_data=request_data,
            response_data=response_data,
            is_successful=is_successful,
            error_message=error_message,
            duration_ms=duration_ms
        )


class TransbankWebPayPlusService(BasePaymentService):
    """
    🚀 ENTERPRISE: Transbank WebPay Plus REST API Service
    Optimized for high concurrency and enterprise reliability.
    """
    
    def __init__(self, provider: PaymentProvider):
        super().__init__(provider)
        
        # 🚀 ENTERPRISE: Correct Transbank REST API endpoints
        if self.is_sandbox:
            self.base_url = "https://webpay3gint.transbank.cl/rswebpaytransaction/api/webpay/v1.2"
        else:
            self.base_url = "https://webpay3g.transbank.cl/rswebpaytransaction/api/webpay/v1.2"
        
        # Configuration
        self.commerce_code = self.config.get('commerce_code')
        self.api_key = self.config.get('api_key')
        
        if not self.commerce_code or not self.api_key:
            raise PaymentServiceException("Transbank configuration missing: commerce_code or api_key")
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict[str, Any]:
        """
        🚀 ENTERPRISE: Optimized HTTP client with retry logic and monitoring
        """
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'Tbk-Api-Key-Id': self.commerce_code,
            'Tbk-Api-Key-Secret': self.api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        start_time = time.time()
        last_exception = None
        
        for attempt in range(self.retry_attempts):
            try:
                logger.info(f"🌐 TRANSBANK: {method} {url} (attempt {attempt + 1})")
                logger.info(f"🌐 TRANSBANK: Headers: {headers}")
                logger.info(f"🌐 TRANSBANK: Data: {data}")
                
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    timeout=self.timeout
                )
                
                logger.info(f"🌐 TRANSBANK: Response status: {response.status_code}")
                logger.info(f"🌐 TRANSBANK: Response headers: {dict(response.headers)}")
                logger.info(f"🌐 TRANSBANK: Response text: {response.text[:500]}...")
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ TRANSBANK: Success in {duration_ms}ms")
                    return {
                        'success': True,
                        'data': result,
                        'duration_ms': duration_ms,
                        'status_code': response.status_code
                    }
                else:
                    error_data = response.text
                    try:
                        error_data = response.json()
                    except:
                        pass
                    
                    logger.error(f"❌ TRANSBANK: HTTP {response.status_code} - {error_data}")
                    return {
                        'success': False,
                        'error': error_data,
                        'duration_ms': duration_ms,
                        'status_code': response.status_code
                    }
                    
            except requests.exceptions.Timeout:
                last_exception = f"Timeout after {self.timeout}s"
                logger.warning(f"⏰ TRANSBANK: Timeout on attempt {attempt + 1}")
                
            except requests.exceptions.ConnectionError:
                last_exception = "Connection error"
                logger.warning(f"🔌 TRANSBANK: Connection error on attempt {attempt + 1}")
                
            except Exception as e:
                last_exception = str(e)
                logger.error(f"💥 TRANSBANK: Unexpected error on attempt {attempt + 1}: {e}")
                
            # Wait before retry (exponential backoff)
            if attempt < self.retry_attempts - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
        
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            'success': False,
            'error': f"All {self.retry_attempts} attempts failed. Last error: {last_exception}",
            'duration_ms': duration_ms,
            'status_code': 0
        }
    
    def create_payment(self, order, amount: Decimal, payment_method: PaymentMethod) -> Payment:
        """Create a new WebPay Plus payment"""
        with transaction.atomic():
            payment = Payment.objects.create(
                order=order,
                payment_method=payment_method,
                amount=amount,
                currency='CLP',
                status='pending'
            )
            payment.generate_buy_order()
            payment.save()
            
            return payment
    
    def process_payment(self, payment: Payment) -> Dict[str, Any]:
        """
        🚀 ENTERPRISE: Create WebPay Plus transaction
        """
        # Prepare request data
        request_data = {
            'buy_order': payment.buy_order,
            'session_id': str(payment.id),
            'amount': float(payment.amount),
            'return_url': self._get_return_url(payment)
        }
        
        start_time = time.time()
        
        try:
            # Make API call
            response = self._make_request('POST', 'transactions', request_data)
            duration_ms = response.get('duration_ms', 0)
            
            if response['success']:
                data = response['data']
                
                # Update payment with Transbank data
                payment.token = data.get('token', '')
                payment.external_id = data.get('token', '')
                payment.status = 'processing'
                payment.metadata.update({
                    'transbank_response': data,
                    'created_at': timezone.now().isoformat()
                })
                payment.save()
                
                # Log successful transaction
                self.log_transaction(
                    payment=payment,
                    transaction_type='create',
                    request_data=request_data,
                    response_data=data,
                    is_successful=True,
                    duration_ms=duration_ms
                )
                
                # 🚀 ENTERPRISE FIX: Construct complete payment URL with token
                base_payment_url = data.get('url', '')
                token = data.get('token', '')
                payment_url = f"{base_payment_url}?token_ws={token}" if token else base_payment_url
                
                return {
                    'success': True,
                    'payment_url': payment_url,
                    'token': token,
                    'payment': payment
                }
            else:
                # Log failed transaction
                self.log_transaction(
                    payment=payment,
                    transaction_type='create',
                    request_data=request_data,
                    response_data=response.get('error', {}),
                    is_successful=False,
                    error_message=str(response.get('error', 'Unknown error')),
                    duration_ms=duration_ms
                )
                
                payment.status = 'failed'
                payment.save()
                
                return {
                    'success': False,
                    'error': response.get('error', 'Unknown error'),
                    'payment': payment
                }
                
        except Exception as e:
            logger.error(f"💥 TRANSBANK: Unexpected error processing payment {payment.buy_order}: {e}")
            
            # Log exception
            self.log_transaction(
                payment=payment,
                transaction_type='create',
                request_data=request_data,
                response_data={},
                is_successful=False,
                error_message=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )
            
            payment.status = 'failed'
            payment.save()
            
            return {
                'success': False,
                'error': str(e),
                'payment': payment
            }
    
    def confirm_payment(self, token: str) -> Dict[str, Any]:
        """
        🚀 ENTERPRISE: Confirm WebPay Plus transaction after user returns
        """
        try:
            payment = Payment.objects.get(token=token)
        except Payment.DoesNotExist:
            return {
                'success': False,
                'error': 'Payment not found'
            }
        
        start_time = time.time()
        
        try:
            # Confirm transaction with Transbank
            response = self._make_request('PUT', f'transactions/{token}')
            duration_ms = response.get('duration_ms', 0)
            
            if response['success']:
                data = response['data']
                response_code = data.get('response_code', -1)
                
                # Update payment status based on response
                if response_code == 0:  # Success
                    payment.status = 'completed'
                    payment.completed_at = timezone.now()
                    payment.metadata.update({
                        'confirmation_response': data,
                        'authorization_code': data.get('authorization_code'),
                        'card_detail': data.get('card_detail', {}),
                        'confirmed_at': timezone.now().isoformat()
                    })
                else:
                    payment.status = 'failed'
                    payment.metadata.update({
                        'failure_response': data,
                        'response_code': response_code
                    })
                
                payment.save()
                
                # Log transaction
                self.log_transaction(
                    payment=payment,
                    transaction_type='authorize',
                    request_data={'token': token},
                    response_data=data,
                    is_successful=(response_code == 0),
                    duration_ms=duration_ms
                )
                
            # Update order status if payment successful
            if payment.status == 'completed':
                # 🚀 ENTERPRISE: Get flow from order for tracking
                from core.flow_logger import FlowLogger
                flow = FlowLogger.from_flow_id(payment.order.flow_id) if payment.order.flow_id else None
                
                # Log payment authorized
                if flow:
                    flow.log_event(
                        'PAYMENT_AUTHORIZED',
                        source='payment_gateway',
                        status='success',
                        order=payment.order,
                        payment=payment,
                        message=f"Payment {payment.buy_order} authorized successfully",
                        metadata={
                            'amount': float(payment.amount),
                            'buy_order': payment.buy_order,
                            'authorization_code': data.get('authorization_code'),
                            'payment_type_code': data.get('payment_type_code')
                        }
                    )
                
                payment.order.status = 'paid'
                payment.order.save()
                
                # Log order marked as paid
                if flow:
                    flow.log_event(
                        'ORDER_MARKED_PAID',
                        order=payment.order,
                        payment=payment,
                        status='success',
                        message=f"Order {payment.order.order_number} marked as paid",
                        metadata={'total': float(payment.order.total)}
                    )
                
                # ✅ Domain-specific post-payment handling
                order_kind = getattr(payment.order, 'order_kind', 'event')
                if order_kind == 'experience':
                    # Mark experience reservation paid and keep holds until the instance ends
                    try:
                        reservation = payment.order.experience_reservation
                        if reservation:
                            reservation.status = 'paid'
                            reservation.paid_at = timezone.now()
                            reservation.save(update_fields=['status', 'paid_at'])

                            # Extend holds so capacity/resources remain reserved until the experience ends
                            end_dt = getattr(reservation.instance, 'end_datetime', None)
                            if end_dt:
                                reservation.capacity_holds.filter(released=False).update(expires_at=end_dt)
                                reservation.resource_holds.filter(released=False).update(expires_at=end_dt)
                            
                            logger.info(f"✅ [PAYMENT] Experience reservation {reservation.reservation_id} marked as paid")
                            # Notify creator by email when sale was with their link
                            if reservation.creator_id:
                                try:
                                    from apps.experiences.tasks import notify_creator_on_sale
                                    notify_creator_on_sale.apply_async(
                                        args=[str(reservation.id)],
                                        queue='emails',
                                    )
                                except Exception:
                                    logger.exception("Failed to enqueue creator sale notification")
                            # Notify operator and customer via WhatsApp
                            try:
                                from apps.whatsapp.services.payment_success_notifier import (
                                    notify_operator_payment_received,
                                    notify_customer_payment_success,
                                )
                                from apps.experiences.receipt_generator import ExperienceReceiptGenerator
                                notify_operator_payment_received(payment)
                                receipt_b64 = ExperienceReceiptGenerator.generate_receipt_base64(
                                    payment.order, reservation
                                )
                                notify_customer_payment_success(payment, receipt_base64=receipt_b64)
                            except Exception:
                                logger.exception("WhatsApp payment notifications failed")
                    except Exception:
                        logger.exception("Failed to finalize experience reservation after payment")
                elif order_kind == 'accommodation':
                    try:
                        finalize_accommodation_payment(payment)
                    except Exception:
                        logger.exception("Failed to finalize accommodation reservation after payment")
                elif order_kind == 'car_rental':
                    try:
                        finalize_car_rental_payment(payment)
                    except Exception:
                        logger.exception("Failed to finalize car_rental reservation after payment")
                elif order_kind == 'erasmus_activity':
                    try:
                        link = payment.order.erasmus_activity_payment_link
                        if link:
                            from apps.erasmus.models import ErasmusActivityInscriptionPayment
                            ErasmusActivityInscriptionPayment.objects.update_or_create(
                                lead=link.lead,
                                instance=link.instance,
                                defaults={
                                    "amount": link.amount,
                                    "payment_method": "platform",
                                    "paid_at": timezone.now(),
                                },
                            )
                            logger.info(
                                "Erasmus inscription marked as paid (platform): lead=%s instance=%s",
                                link.lead_id, link.instance_id,
                            )
                    except Exception:
                        logger.exception("Failed to finalize erasmus_activity payment")
                else:
                    # Event: create tickets from reservations
                    self._create_tickets_from_reservations(payment.order)
                
                # Log tickets created + cleanup only for event orders (not experience, accommodation, car_rental)
                if order_kind not in ('experience', 'accommodation', 'car_rental', 'erasmus_activity'):
                    if flow:
                        tickets_count = payment.order.items.aggregate(total=models.Sum('quantity'))['total'] or 0
                        flow.log_event(
                            'TICKETS_CREATED',
                            order=payment.order,
                            status='success',
                            message=f"{tickets_count} tickets created for order {payment.order.order_number}",
                            metadata={'tickets_count': tickets_count}
                        )

                    # ✅ CLEANUP: Limpiar holds y reservations (tickets)
                    self._cleanup_order_reservations(payment.order)
                
                # 🚀 ENTERPRISE: Email will be sent synchronously from frontend confirmation page
                # This reduces latency from 5+ minutes to <10 seconds
                # If frontend sync send fails, it will automatically fallback to Celery
                if flow:
                    flow_type = 'paid_experience' if getattr(payment.order, 'order_kind', 'event') == 'experience' else ('paid_car_rental' if getattr(payment.order, 'order_kind', '') == 'car_rental' else 'paid_order')
                    flow.log_event(
                        'EMAIL_PENDING',
                        order=payment.order,
                        status='info',
                        message=f"Email pending - will be sent from confirmation page for order {payment.order.order_number}",
                        metadata={
                            'email_strategy': 'frontend_sync',
                            'fallback_to_celery': True,
                            'flow_type': flow_type
                        }
                    )
                logger.info(f"📧 [EMAIL] Email marked as pending for order {payment.order.id} - will be sent from frontend")
                
                # Complete flow
                if flow:
                    flow.complete(message=f"Order {payment.order.order_number} completed successfully")
                
                return {
                    'success': True,
                    'payment': payment,
                    'transaction_data': data
                }
            else:
                # Log failed confirmation
                self.log_transaction(
                    payment=payment,
                    transaction_type='authorize',
                    request_data={'token': token},
                    response_data=response.get('error', {}),
                    is_successful=False,
                    error_message=str(response.get('error')),
                    duration_ms=duration_ms
                )
                
                payment.status = 'failed'
                payment.save()
                
                # 🚀 ENTERPRISE: Release holds immediately when payment fails
                from apps.events.models import TicketHold
                expired_holds = TicketHold.objects.filter(
                    order=payment.order,
                    released=False
                )
                for hold in expired_holds:
                    hold.release()  # Returns tickets to availability
                
                return {
                    'success': False,
                    'error': response.get('error'),
                    'payment': payment
                }
                
        except Exception as e:
            logger.error(f"💥 TRANSBANK: Error confirming payment {token}: {e}")
            
            self.log_transaction(
                payment=payment,
                transaction_type='authorize',
                request_data={'token': token},
                response_data={},
                is_successful=False,
                error_message=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )
            
            return {
                'success': False,
                'error': str(e),
                'payment': payment
            }
    
    def _get_return_url(self, payment: Payment) -> str:
        """Generate return URL for payment with access token"""
        base_url = settings.FRONTEND_URL or "http://localhost:8080"
        # Get order access token for public ticket access
        order = payment.order
        if order and order.access_token:
            return f"{base_url}/payment/return?token={order.access_token}"
        return f"{base_url}/payment/return"

    def _create_tickets_from_reservations(self, order, flow_logger=None):
        """
        🚀 ENTERPRISE: Create tickets from stored TicketHolderReservation data
        """
        from apps.events.models import TicketHolderReservation, Ticket
        
        print(f"🎫 ENTERPRISE - Creating tickets from reservations for PAID order {order.id}")
        
        # Get all reservations for this order
        reservations = TicketHolderReservation.objects.filter(order=order).order_by('ticket_tier', 'holder_index')
        
        if not reservations.exists():
            print(f"⚠️ ENTERPRISE - No reservations found for order {order.id}. This might be a free order.")
            return
        
        print(f"🎫 ENTERPRISE - Found {reservations.count()} holder reservations")
        
        # Group reservations by order item
        for order_item in order.items.all():
            tier_reservations = reservations.filter(ticket_tier=order_item.ticket_tier)
            print(f"🎫 ENTERPRISE - Processing {tier_reservations.count()} reservations for tier {order_item.ticket_tier.name}")
            
            for reservation in tier_reservations:
                # Create ticket with stored holder data
                created_ticket = Ticket.objects.create(
                    order_item=order_item,
                    first_name=reservation.first_name,
                    last_name=reservation.last_name,
                    email=reservation.email,
                    form_data=reservation.form_data,
                    status='active'
                )
                print(f"🎫 ENTERPRISE - Created ticket {created_ticket.ticket_number}: {created_ticket.first_name} {created_ticket.last_name}")

    def _cleanup_order_reservations(self, order):
        """
        🚀 ENTERPRISE: Clean up holds and reservations after successful payment
        """
        from apps.events.models import TicketHold, TicketHolderReservation
        
        print(f"🧹 ENTERPRISE - Cleaning up reservations for order {order.id}")
        
        # Clean up ticket holds
        holds_deleted = TicketHold.objects.filter(order=order).delete()
        print(f"🧹 ENTERPRISE - Deleted {holds_deleted[0]} ticket holds")
        
        # Clean up holder reservations
        reservations_deleted = TicketHolderReservation.objects.filter(order=order).delete()
        print(f"🧹 ENTERPRISE - Deleted {reservations_deleted[0]} holder reservations")
        
        print(f"✅ ENTERPRISE - Cleanup completed for order {order.id}")


class PaymentServiceFactory:
    """
    🚀 ENTERPRISE: Factory for creating payment services
    """
    
    _services = {
        'transbank_webpay_plus': TransbankWebPayPlusService,
        # Add more services here
        # 'transbank_oneclick': TransbankOneclickService,
        # 'mercadopago': MercadoPagoService,
        # 'stripe': StripeService,
    }
    
    @classmethod
    def create_service(cls, provider: PaymentProvider) -> BasePaymentService:
        """Create payment service for provider"""
        service_class = cls._services.get(provider.provider_type)
        
        if not service_class:
            raise PaymentServiceException(f"No service available for provider: {provider.provider_type}")
        
        return service_class(provider)
    
    @classmethod
    def get_available_providers(cls) -> List[PaymentProvider]:
        """Get all active payment providers"""
        return PaymentProvider.objects.filter(is_active=True).order_by('-priority')
    
    @classmethod
    def get_best_provider_for_amount(cls, amount: Decimal, currency: str = 'CLP') -> Optional[PaymentProvider]:
        """Get the best payment provider for a given amount"""
        providers = cls.get_available_providers()
        
        for provider in providers:
            if currency not in provider.supported_currencies:
                continue
                
            if amount < provider.min_amount:
                continue
                
            if provider.max_amount and amount > provider.max_amount:
                continue
            
            return provider
        
        return None
