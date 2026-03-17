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
from apps.experiences.models import ExperienceReservation
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
            
            # 🚀 ENTERPRISE: Obtener órdenes del usuario - event, experience y accommodation
            orders = Order.objects.filter(
                Q(user=user) | Q(email__iexact=user.email),
                status__in=['paid']
            ).select_related(
                'event', 'event__location', 'experience_reservation',
                'experience_reservation__experience', 'experience_reservation__instance',
                'accommodation_reservation', 'accommodation_reservation__accommodation',
                'car_rental_reservation', 'car_rental_reservation__car', 'car_rental_reservation__car__company',
            ).prefetch_related('items__ticket_tier', 'items__tickets', 'event__images').order_by('-created_at')
            
            logger.info(f"[UserReservationsView] User: {user.email} (ID: {user.id}), orders: {orders.count()}")
            
            reservations = []
            for order in orders:
                try:
                    event = order.event
                    exp_res = getattr(order, 'experience_reservation', None)
                    acc_res = getattr(order, 'accommodation_reservation', None)
                    car_res = getattr(order, 'car_rental_reservation', None)

                    # Car rental order (car_rental_reservation exists)
                    if car_res:
                        car = car_res.car
                        event_image = None
                        if car and getattr(car, 'gallery_media_ids', None) and len(car.gallery_media_ids) > 0:
                            from apps.media.models import MediaAsset
                            first_id = car.gallery_media_ids[0]
                            asset = MediaAsset.objects.filter(id=first_id, deleted_at__isnull=True).first()
                            if asset and getattr(asset, 'file', None):
                                event_image = asset.file.url
                        if not event_image and car and getattr(car, 'images', None) and len(car.images) > 0:
                            img = car.images[0]
                            event_image = img if isinstance(img, str) else (img.get('url') if isinstance(img, dict) else None)
                        company_name = car.company.name if car and car.company else ''
                        reservation = {
                            'id': str(car_res.id),
                            'orderId': order.order_number,
                            'eventId': str(car.id) if car else str(car_res.id),
                            'eventTitle': car.title if car else 'Auto',
                            'eventImage': event_image,
                            'eventDate': car_res.pickup_date.strftime('%d %B %Y') if car_res.pickup_date else '',
                            'eventTime': car_res.pickup_time or '',
                            'date': car_res.pickup_date.isoformat() if car_res.pickup_date else order.created_at.isoformat(),
                            'location': company_name or 'Ubicación no especificada',
                            'status': 'confirmed' if car_res.status == 'paid' else car_res.status,
                            'totalAmount': float(order.total),
                            'subtotal': float(order.subtotal),
                            'serviceFee': float(order.service_fee),
                            'discount': float(order.discount or 0),
                            'currency': order.currency,
                            'ticketCount': 1,
                            'tickets': [],
                            'attendees': [{
                                'name': f"{car_res.first_name} {car_res.last_name}".strip(),
                                'email': car_res.email,
                                'ticketType': 'Auto',
                                'checkIn': f"Retiro: {car_res.pickup_date} {car_res.pickup_time or ''}".strip(),
                                'ticketNumber': car_res.reservation_id,
                            }],
                            'purchaseDate': order.created_at.isoformat(),
                            'type': 'car_rental',
                            'paymentInfo': {'method': 'Transbank', 'provider': 'Webpay', 'status': 'Pagado'},
                            'customerInfo': {
                                'name': f"{car_res.first_name} {car_res.last_name}".strip(),
                                'email': car_res.email,
                                'phone': car_res.phone or '',
                            },
                            'pickupDate': car_res.pickup_date.isoformat() if car_res.pickup_date else None,
                            'returnDate': car_res.return_date.isoformat() if car_res.return_date else None,
                            'pickupTime': car_res.pickup_time or None,
                            'returnTime': car_res.return_time or None,
                        }
                        reservations.append(reservation)
                        continue

                    # Accommodation order (accommodation_reservation exists)
                    if acc_res:
                        acc = acc_res.accommodation
                        event_image = None
                        if acc and getattr(acc, 'images', None) and len(acc.images) > 0:
                            img = acc.images[0]
                            event_image = img if isinstance(img, str) else (img.get('url') if isinstance(img, dict) else None)
                        reservation = {
                            'id': str(acc_res.id),
                            'orderId': order.order_number,
                            'eventId': str(acc.id) if acc else str(acc_res.id),
                            'eventTitle': acc.title if acc else 'Alojamiento',
                            'eventImage': event_image,
                            'eventDate': acc_res.check_in.strftime('%d %B %Y') if acc_res.check_in else '',
                            'eventTime': '',
                            'date': acc_res.check_in.isoformat() if acc_res.check_in else order.created_at.isoformat(),
                            'location': getattr(acc, 'location_name', None) or getattr(acc, 'city', '') or getattr(acc, 'country', '') or 'Ubicación no especificada',
                            'status': 'confirmed' if acc_res.status == 'paid' else acc_res.status,
                            'totalAmount': float(order.total),
                            'subtotal': float(order.subtotal),
                            'serviceFee': float(order.service_fee),
                            'discount': float(order.discount or 0),
                            'currency': order.currency,
                            'ticketCount': acc_res.guests,
                            'tickets': [],
                            'attendees': [{
                                'name': f"{acc_res.first_name} {acc_res.last_name}".strip(),
                                'email': acc_res.email,
                                'ticketType': 'Alojamiento',
                                'checkIn': f"Check-in: {acc_res.check_in}" if acc_res.check_in else '',
                                'ticketNumber': acc_res.reservation_id,
                            }],
                            'purchaseDate': order.created_at.isoformat(),
                            'type': 'accommodation',
                            'paymentInfo': {'method': 'Transbank', 'provider': 'Webpay', 'status': 'Pagado'},
                            'customerInfo': {
                                'name': f"{acc_res.first_name} {acc_res.last_name}".strip(),
                                'email': acc_res.email,
                                'phone': acc_res.phone or '',
                            },
                            'checkIn': acc_res.check_in.isoformat() if acc_res.check_in else None,
                            'checkOut': acc_res.check_out.isoformat() if acc_res.check_out else None,
                        }
                        reservations.append(reservation)
                        continue

                    # Experience order (experience_reservation exists)
                    if exp_res:
                        experience = exp_res.experience
                        instance = getattr(exp_res, 'instance', None)
                        start_dt = instance.start_datetime if instance else None
                        ticket_count = (exp_res.adult_count or 0) + (exp_res.child_count or 0) + (exp_res.infant_count or 0) or 1
                        event_image = None
                        if experience and getattr(experience, 'images', None) and len(experience.images) > 0:
                            event_image = experience.images[0] if isinstance(experience.images[0], str) else experience.images[0].get('url', None)
                        reservation = {
                            'id': str(exp_res.id),
                            'orderId': order.order_number,
                            'eventId': str(experience.id) if experience else str(exp_res.id),
                            'eventTitle': experience.title if experience else 'Experiencia',
                            'eventImage': event_image,
                            'eventDate': start_dt.strftime('%d %B %Y') if start_dt else '',
                            'eventTime': start_dt.strftime('%H:%M') if start_dt else '',
                            'date': start_dt.isoformat() if start_dt else order.created_at.isoformat(),
                            'location': getattr(experience, 'location_name', None) or getattr(experience, 'location_address', '') or 'Ubicación no especificada',
                            'status': 'confirmed' if exp_res.status == 'paid' else exp_res.status,
                            'totalAmount': float(order.total),
                            'subtotal': float(order.subtotal),
                            'serviceFee': float(order.service_fee),
                            'discount': float(order.discount or 0),
                            'currency': order.currency,
                            'ticketCount': ticket_count,
                            'tickets': [],
                            'attendees': [{
                                'name': f"{exp_res.first_name} {exp_res.last_name}".strip(),
                                'email': exp_res.email,
                                'ticketType': 'Experiencia',
                                'checkIn': '',
                                'ticketNumber': exp_res.reservation_id
                            }],
                            'purchaseDate': order.created_at.isoformat(),
                            'type': 'experience',
                            'paymentInfo': {'method': 'Transbank', 'provider': 'Webpay', 'status': 'Pagado'},
                            'customerInfo': {
                                'name': f"{exp_res.first_name} {exp_res.last_name}".strip(),
                                'email': exp_res.email,
                                'phone': exp_res.phone or ''
                            }
                        }
                        reservations.append(reservation)
                        continue
                    
                    # Event order (event exists)
                    if not event:
                        continue
                    
                    event_image = None
                    if event.images.exists():
                        first_image = event.images.first()
                        if first_image and hasattr(first_image, 'image') and first_image.image:
                            event_image = first_image.image.url
                    
                    ticket_count = 0
                    tickets = []
                    attendees = []
                    for item in order.items.all():
                        ticket_count += item.quantity
                        tickets.append({
                            'id': item.id,
                            'tierName': item.ticket_tier.name if item.ticket_tier else 'General',
                            'quantity': item.quantity,
                            'unitPrice': float(item.unit_price),
                            'subtotal': float(item.subtotal),
                            'status': 'Válido' if order.status == 'paid' else 'Pendiente'
                        })
                        for ticket in item.tickets.all():
                            attendees.append({
                                'name': f"{ticket.first_name} {ticket.last_name}".strip(),
                                'email': ticket.email,
                                'ticketType': item.ticket_tier.name if item.ticket_tier else 'General',
                                'checkIn': ticket.check_in_status or 'Pendiente',
                                'ticketNumber': ticket.ticket_number
                            })
                    
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
    Vista para obtener detalles de una reserva específica.
    reservation_id puede ser Order.id o accommodation_reservation.id / experience_reservation.id / car_rental_reservation.id.
    """
    permission_classes = [IsAuthenticated]

    def _get_order(self, user, reservation_id):
        """Resolve Order by id or by linked reservation id."""
        base_q = Q(user=user) | Q(email__iexact=user.email)
        # Try as Order.id
        order = Order.objects.filter(base_q).filter(id=reservation_id).select_related(
            'event', 'event__location', 'accommodation_reservation', 'accommodation_reservation__accommodation',
            'experience_reservation', 'experience_reservation__experience', 'experience_reservation__instance',
            'car_rental_reservation', 'car_rental_reservation__car', 'car_rental_reservation__car__company',
        ).prefetch_related('items__ticket_tier', 'items__tickets', 'event__images').first()
        if order:
            return order
        # Try as car_rental_reservation_id
        order = Order.objects.filter(base_q).filter(car_rental_reservation_id=reservation_id).select_related(
            'car_rental_reservation', 'car_rental_reservation__car', 'car_rental_reservation__car__company',
        ).first()
        if order:
            return order
        # Try as accommodation_reservation_id
        order = Order.objects.filter(base_q).filter(accommodation_reservation_id=reservation_id).select_related(
            'accommodation_reservation', 'accommodation_reservation__accommodation',
        ).first()
        if order:
            return order
        # Try as experience_reservation_id
        order = Order.objects.filter(base_q).filter(experience_reservation_id=reservation_id).select_related(
            'experience_reservation', 'experience_reservation__experience', 'experience_reservation__instance',
        ).first()
        return order

    def _build_accommodation_reservation(self, order):
        """Build reservation dict for accommodation (same shape as list)."""
        acc_res = order.accommodation_reservation
        acc = acc_res.accommodation
        event_image = None
        if acc and getattr(acc, 'images', None) and len(acc.images) > 0:
            img = acc.images[0]
            event_image = img if isinstance(img, str) else (img.get('url') if isinstance(img, dict) else None)
        return {
            'id': str(acc_res.id),
            'orderId': order.order_number,
            'eventId': str(acc.id) if acc else str(acc_res.id),
            'eventTitle': acc.title if acc else 'Alojamiento',
            'eventImage': event_image,
            'eventDate': acc_res.check_in.strftime('%d %B %Y') if acc_res.check_in else '',
            'eventTime': '',
            'date': acc_res.check_in.isoformat() if acc_res.check_in else order.created_at.isoformat(),
            'location': getattr(acc, 'location_name', None) or getattr(acc, 'city', '') or getattr(acc, 'country', '') or 'Ubicación no especificada',
            'status': 'confirmed' if acc_res.status == 'paid' else acc_res.status,
            'totalAmount': float(order.total),
            'subtotal': float(order.subtotal),
            'serviceFee': float(order.service_fee),
            'discount': float(order.discount or 0),
            'currency': order.currency,
            'ticketCount': acc_res.guests,
            'tickets': [],
            'attendees': [{
                'name': f"{acc_res.first_name} {acc_res.last_name}".strip(),
                'email': acc_res.email,
                'ticketType': 'Alojamiento',
                'checkIn': f"Check-in: {acc_res.check_in}" if acc_res.check_in else '',
                'ticketNumber': acc_res.reservation_id,
            }],
            'purchaseDate': order.created_at.isoformat(),
            'type': 'accommodation',
            'paymentInfo': {'method': 'Transbank', 'provider': 'Webpay', 'status': 'Pagado'},
            'customerInfo': {
                'name': f"{acc_res.first_name} {acc_res.last_name}".strip(),
                'email': acc_res.email,
                'phone': acc_res.phone or '',
            },
            'checkIn': acc_res.check_in.isoformat() if acc_res.check_in else None,
            'checkOut': acc_res.check_out.isoformat() if acc_res.check_out else None,
            'pricing_snapshot': getattr(acc_res, 'pricing_snapshot', None),
        }

    def _build_experience_reservation(self, order):
        """Build reservation dict for experience (same shape as list)."""
        exp_res = order.experience_reservation
        experience = exp_res.experience
        instance = getattr(exp_res, 'instance', None)
        start_dt = instance.start_datetime if instance else None
        ticket_count = (exp_res.adult_count or 0) + (exp_res.child_count or 0) + (exp_res.infant_count or 0) or 1
        event_image = None
        if experience and getattr(experience, 'images', None) and len(experience.images) > 0:
            event_image = experience.images[0] if isinstance(experience.images[0], str) else experience.images[0].get('url', None)
        return {
            'id': str(exp_res.id),
            'orderId': order.order_number,
            'eventId': str(experience.id) if experience else str(exp_res.id),
            'eventTitle': experience.title if experience else 'Experiencia',
            'eventImage': event_image,
            'eventDate': start_dt.strftime('%d %B %Y') if start_dt else '',
            'eventTime': start_dt.strftime('%H:%M') if start_dt else '',
            'date': start_dt.isoformat() if start_dt else order.created_at.isoformat(),
            'location': getattr(experience, 'location_name', None) or getattr(experience, 'location_address', '') or 'Ubicación no especificada',
            'status': 'confirmed' if exp_res.status == 'paid' else exp_res.status,
            'totalAmount': float(order.total),
            'subtotal': float(order.subtotal),
            'serviceFee': float(order.service_fee),
            'discount': float(order.discount or 0),
            'currency': order.currency,
            'ticketCount': ticket_count,
            'tickets': [],
            'attendees': [{
                'name': f"{exp_res.first_name} {exp_res.last_name}".strip(),
                'email': exp_res.email,
                'ticketType': 'Experiencia',
                'checkIn': '',
                'ticketNumber': exp_res.reservation_id
            }],
            'purchaseDate': order.created_at.isoformat(),
            'type': 'experience',
            'paymentInfo': {'method': 'Transbank', 'provider': 'Webpay', 'status': 'Pagado'},
            'customerInfo': {
                'name': f"{exp_res.first_name} {exp_res.last_name}".strip(),
                'email': exp_res.email,
                'phone': exp_res.phone or ''
            }
        }

    def _build_car_rental_reservation(self, order):
        """Build reservation dict for car_rental (same shape as list)."""
        car_res = order.car_rental_reservation
        car = car_res.car
        event_image = None
        if car and getattr(car, 'gallery_media_ids', None) and len(car.gallery_media_ids) > 0:
            from apps.media.models import MediaAsset
            first_id = car.gallery_media_ids[0]
            asset = MediaAsset.objects.filter(id=first_id, deleted_at__isnull=True).first()
            if asset and getattr(asset, 'file', None):
                event_image = asset.file.url
        if not event_image and car and getattr(car, 'images', None) and len(car.images) > 0:
            img = car.images[0]
            event_image = img if isinstance(img, str) else (img.get('url') if isinstance(img, dict) else None)
        company_name = car.company.name if car and car.company else ''
        return {
            'id': str(car_res.id),
            'orderId': order.order_number,
            'eventId': str(car.id) if car else str(car_res.id),
            'eventTitle': car.title if car else 'Auto',
            'eventImage': event_image,
            'eventDate': car_res.pickup_date.strftime('%d %B %Y') if car_res.pickup_date else '',
            'eventTime': car_res.pickup_time or '',
            'date': car_res.pickup_date.isoformat() if car_res.pickup_date else order.created_at.isoformat(),
            'location': company_name or 'Ubicación no especificada',
            'status': 'confirmed' if car_res.status == 'paid' else car_res.status,
            'totalAmount': float(order.total),
            'subtotal': float(order.subtotal),
            'serviceFee': float(order.service_fee),
            'discount': float(order.discount or 0),
            'currency': order.currency,
            'ticketCount': 1,
            'tickets': [],
            'attendees': [{
                'name': f"{car_res.first_name} {car_res.last_name}".strip(),
                'email': car_res.email,
                'ticketType': 'Auto',
                'checkIn': f"Retiro: {car_res.pickup_date} {car_res.pickup_time or ''}".strip(),
                'ticketNumber': car_res.reservation_id,
            }],
            'purchaseDate': order.created_at.isoformat(),
            'type': 'car_rental',
            'paymentInfo': {'method': 'Transbank', 'provider': 'Webpay', 'status': 'Pagado'},
            'customerInfo': {
                'name': f"{car_res.first_name} {car_res.last_name}".strip(),
                'email': car_res.email,
                'phone': car_res.phone or '',
            },
            'pickupDate': car_res.pickup_date.isoformat() if car_res.pickup_date else None,
            'returnDate': car_res.return_date.isoformat() if car_res.return_date else None,
            'pickupTime': car_res.pickup_time or None,
            'returnTime': car_res.return_time or None,
        }

    def get(self, request, reservation_id):
        try:
            user = request.user
            order = self._get_order(user, reservation_id)
            if not order:
                return Response({
                    'success': False,
                    'message': 'Reserva no encontrada'
                }, status=status.HTTP_404_NOT_FOUND)

            if getattr(order, 'car_rental_reservation', None):
                reservation = self._build_car_rental_reservation(order)
                return Response({'success': True, 'reservation': reservation}, status=status.HTTP_200_OK)
            if getattr(order, 'accommodation_reservation', None):
                reservation = self._build_accommodation_reservation(order)
                return Response({'success': True, 'reservation': reservation}, status=status.HTTP_200_OK)
            if getattr(order, 'experience_reservation', None):
                reservation = self._build_experience_reservation(order)
                return Response({'success': True, 'reservation': reservation}, status=status.HTTP_200_OK)

            # Event order: use serializer
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