from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.events.models import Event, Order, OrderItem
from .serializers import UserReservationSerializer
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class UserViewSet(ModelViewSet):
    """ViewSet para usuarios (compatibilidad)"""
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        from api.v1.auth.serializers import UserProfileSerializer
        return UserProfileSerializer


class UserReservationsView(APIView):
    """
    Vista para obtener las reservas del usuario autenticado
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            
            # 🚀 ENTERPRISE: Obtener órdenes del usuario - tanto las vinculadas por user_id como por email
            # Esto permite mostrar compras hechas como invitado antes de registrarse
            orders = Order.objects.filter(
                Q(user=user) | Q(email__iexact=user.email),  # Órdenes vinculadas al user O al email
                status__in=['paid']
            ).select_related('event', 'event__location').prefetch_related('items__ticket_tier', 'event__images').order_by('-created_at')
            
            print(f"🔍 [UserReservationsView] User: {user.email} (ID: {user.id})")
            print(f"🔍 [UserReservationsView] Found {orders.count()} orders for user")
            
            # 🚀 ENTERPRISE: Serializar reservas usando modelo completo
            reservations = []
            for order in orders:
                try:
                    # Obtener información del evento
                    event = order.event
                    if not event:
                        continue
                    
                    # 🎯 ENTERPRISE: Obtener imagen del evento correctamente
                    event_image = None
                    if event.images.exists():
                        first_image = event.images.first()
                        if first_image and hasattr(first_image, 'image') and first_image.image:
                            event_image = first_image.image.url
                    
                    # 🎯 ENTERPRISE: Construir información de tickets y asistentes reales
                    ticket_count = 0
                    tickets = []
                    attendees = []
                    
                    for item in order.items.all():
                        ticket_count += item.quantity
                        
                        # Información del ticket tier
                        tickets.append({
                            'id': item.id,
                            'tierName': item.ticket_tier.name if item.ticket_tier else 'General',
                            'quantity': item.quantity,
                            'unitPrice': float(item.unit_price),
                            'subtotal': float(item.subtotal),
                            'status': 'Válido' if order.status == 'paid' else 'Pendiente'
                        })
                        
                        # 🎯 ENTERPRISE: Obtener asistentes reales de los tickets
                        for ticket in item.tickets.all():
                            attendees.append({
                                'name': f"{ticket.first_name} {ticket.last_name}".strip(),
                                'email': ticket.email,
                                'ticketType': item.ticket_tier.name if item.ticket_tier else 'General',
                                'checkIn': ticket.check_in_status or 'Pendiente',
                                'ticketNumber': ticket.ticket_number
                            })
                    
                    # 🎯 ENTERPRISE: Información de pago (basada en modelo real)
                    payment_info = {
                        'method': order.payment_method or 'Método desconocido',
                        'provider': 'Transbank' if order.payment_method else 'Desconocido',
                        'status': 'Pagado' if order.status == 'paid' else 'Pendiente'
                    }
                    
                    reservation = {
                        'id': order.id,
                        'orderId': order.order_number,
                        'eventId': event.id,
                        'eventTitle': event.title,
                        'eventImage': event_image,
                        'eventDate': event.start_date.strftime('%d %B %Y'),
                        'eventTime': event.start_date.strftime('%H:%M'),
                        'date': event.start_date.isoformat(),
                        'location': event.location.name if event.location else 'Ubicación no especificada',
                        'status': 'confirmed' if order.status == 'paid' else order.status,
                        'totalAmount': float(order.total),
                        'subtotal': float(order.subtotal),
                        'serviceFee': float(order.service_fee),
                        'discount': float(order.discount) if order.discount else 0,
                        'currency': order.currency,
                        'ticketCount': ticket_count,
                        'tickets': tickets,
                        'attendees': attendees,
                        'purchaseDate': order.created_at.isoformat(),
                        'type': 'event',
                        'paymentInfo': payment_info,
                        # 🎯 ENTERPRISE: Información del cliente
                        'customerInfo': {
                            'name': f"{order.first_name} {order.last_name}".strip(),
                            'email': order.email,
                            'phone': order.phone or ''
                        }
                    }
                    
                    reservations.append(reservation)
                    
                except Exception as e:
                    logger.error(f"Error processing order {order.id}: {str(e)}")
                    continue
            
            return Response({
                'success': True,
                'results': reservations,
                'count': len(reservations)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting user reservations: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error al obtener reservas'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ReservationDetailView(APIView):
    """
    Vista para obtener detalles de una reserva específica
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, reservation_id):
        try:
            user = request.user
            
            # 🚀 ENTERPRISE: Obtener la orden - tanto vinculada por user_id como por email
            order = Order.objects.select_related('event', 'event__location').prefetch_related('items__ticket_tier', 'event__images').get(
                Q(user=user) | Q(email__iexact=user.email),
                id=reservation_id
            )
            
            # Serializar la reserva
            serializer = UserReservationSerializer(order)
            
            return Response({
                'success': True,
                'reservation': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Order.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Reserva no encontrada'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error getting reservation detail: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error al obtener reserva'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def get_reservations_by_email_otp(request):
    """
    Obtener reservas por email usando OTP (para invitados)
    """
    email = request.data.get('email')
    otp_token = request.data.get('otp_token')
    
    if not email or not otp_token:
        return Response({
            'success': False,
            'message': 'Email y token OTP requeridos'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Verificar que el OTP token sea válido
        # TODO: Implementar verificación de token OTP para acceso a tickets
        
        # Obtener órdenes por email
        orders = Order.objects.filter(
            email__iexact=email,
            status__in=['paid']
        ).select_related('event', 'event__location').prefetch_related('items__ticket_tier', 'event__images').order_by('-created_at')
        
        reservations = []
        for order in orders:
            try:
                event = order.event
                if not event:
                    continue
                
                ticket_count = sum(item.quantity for item in order.items.all())
                
                reservation = {
                    'id': order.id,
                    'orderId': order.order_number,
                    'eventId': event.id,
                    'eventTitle': event.title,
                    'eventImage': event.images.first().url if event.images.exists() else None,
                    'eventDate': event.start_date.strftime('%d %B %Y'),
                    'eventTime': event.start_date.strftime('%H:%M'),
                    'location': event.location.name,
                    'status': 'confirmed',
                    'totalAmount': float(order.total),
                    'currency': order.currency,
                    'ticketCount': ticket_count,
                    'purchaseDate': order.created_at.isoformat()
                }
                
                reservations.append(reservation)
                
            except Exception as e:
                logger.error(f"Error processing order {order.id}: {str(e)}")
                continue
        
        return Response({
            'success': True,
            'results': reservations,
            'count': len(reservations)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting reservations by email: {str(e)}")
        return Response({
            'success': False,
            'message': 'Error al obtener reservas'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)