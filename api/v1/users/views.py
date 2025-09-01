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
            
            # Obtener órdenes del usuario
            orders = Order.objects.filter(
                customer_email__iexact=user.email,
                status__in=['completed', 'confirmed']
            ).select_related('event').prefetch_related('items').order_by('-created_at')
            
            # Serializar reservas
            reservations = []
            for order in orders:
                try:
                    # Obtener información del evento
                    event = order.event
                    if not event:
                        continue
                    
                    # Calcular información de tickets
                    ticket_count = sum(item.quantity for item in order.items.all())
                    tickets = []
                    
                    for item in order.items.all():
                        tickets.append({
                            'id': item.id,
                            'tierName': item.ticket_tier_name or 'General',
                            'quantity': item.quantity,
                            'unitPrice': float(item.unit_price)
                        })
                    
                    reservation = {
                        'id': order.id,
                        'orderId': order.order_number,
                        'eventId': event.id,
                        'eventTitle': event.title,
                        'eventImage': event.images.first().url if event.images.exists() else None,
                        'eventDate': event.start_date.strftime('%d %B %Y'),
                        'eventTime': event.start_date.strftime('%H:%M'),
                        'location': event.location.name,
                        'status': 'confirmed' if order.status == 'completed' else order.status,
                        'totalAmount': float(order.total_amount),
                        'currency': order.currency,
                        'ticketCount': ticket_count,
                        'tickets': tickets,
                        'purchaseDate': order.created_at.isoformat(),
                        'attendees': [{
                            'name': f"{order.customer_first_name} {order.customer_last_name}".strip(),
                            'email': order.customer_email
                        }] if order.customer_first_name else []
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
            
            # Obtener la orden
            order = Order.objects.select_related('event').prefetch_related('items').get(
                id=reservation_id,
                customer_email__iexact=user.email
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
            customer_email__iexact=email,
            status__in=['completed', 'confirmed']
        ).select_related('event').prefetch_related('items').order_by('-created_at')
        
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
                    'totalAmount': float(order.total_amount),
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