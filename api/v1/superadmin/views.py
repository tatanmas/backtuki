"""
Super Admin Views - Enterprise User Management
Endpoints públicos (temporal) para gestión de usuarios.
TODO: Agregar autenticación y permisos de super admin en producción.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny  # TODO: Cambiar a IsAdminUser en producción
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken
import logging

from apps.events.models import Order
from apps.otp.models import OTP, OTPAttempt
from apps.validation.models import ValidatorSession, TicketNote as ValidationTicketNote
from apps.organizers.models import OrganizerUser
from apps.events.models import Ticket, TicketNote
from apps.forms.models import Form
from payment_processor.models import SavedCard
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from apps.sync_woocommerce.models import SyncConfiguration, SyncExecution
from apps.events.models import EventView, ConversionFunnel

logger = logging.getLogger(__name__)
User = get_user_model()


class SuperAdminUserViewSet(viewsets.ViewSet):
    """
    🚀 ENTERPRISE: Super Admin User Management ViewSet
    
    Endpoints robustos para gestión completa de usuarios:
    - Listar usuarios con estadísticas
    - Eliminar usuarios con cascada robusta
    - Suspender/activar usuarios
    - Cambiar contraseñas
    - Impersonar usuarios
    """
    
    permission_classes = [AllowAny]  # TODO: Cambiar a [IsAdminUser] en producción
    
    def list(self, request):
        """
        📋 Listar todos los usuarios con estadísticas completas
        
        GET /api/v1/superadmin/users/
        
        Returns:
            - Lista de usuarios con:
                - Información básica (id, email, nombre, etc.)
                - Estadísticas de compras
                - Último acceso
                - Estado de verificación
                - Total gastado
                - Número de órdenes
        """
        try:
            # Obtener todos los usuarios con estadísticas
            users = User.objects.annotate(
                orders_count=Count('orders', distinct=True),
                total_spent=Sum('orders__total', filter=Q(orders__status='paid'))
            ).select_related('profile').order_by('-date_joined')
            
            users_data = []
            for user in users:
                # Calcular estadísticas adicionales
                paid_orders = Order.objects.filter(user=user, status='paid')
                total_tickets = sum(order.items.aggregate(
                    total=Sum('quantity'))['total'] or 0 for order in paid_orders
                )
                
                # Obtener datos del profile de forma segura
                profile_city = None
                profile_country = None
                try:
                    if hasattr(user, 'profile') and user.profile:
                        profile_city = user.profile.city
                        profile_country = user.profile.country
                except Exception:
                    pass  # Profile no existe, dejar como None
                
                user_data = {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'full_name': user.get_full_name(),
                    'phone_number': user.phone_number or '',
                    'is_active': user.is_active,
                    'is_staff': user.is_staff,
                    'is_superuser': user.is_superuser,
                    'is_organizer': user.is_organizer,
                    'is_validator': user.is_validator,
                    'is_guest': user.is_guest,
                    'date_joined': user.date_joined.isoformat(),
                    'last_login': user.last_login.isoformat() if user.last_login else None,
                    'profile_completed_at': user.profile_completed_at.isoformat() if user.profile_completed_at else None,
                    
                    # Estadísticas
                    'orders_count': user.orders_count or 0,
                    'total_spent': float(user.total_spent or 0),
                    'total_tickets': total_tickets,
                    
                    # Profile info
                    'profile_picture': user.profile_picture.url if user.profile_picture else None,
                    'city': profile_city,
                    'country': profile_country,
                    
                    # Email verification
                    'email_verified': EmailAddress.objects.filter(
                        user=user, 
                        verified=True
                    ).exists() if hasattr(EmailAddress, 'objects') else False,
                }
                
                users_data.append(user_data)
            
            logger.info(f"✅ [SuperAdmin] Listed {len(users_data)} users")
            
            return Response({
                'success': True,
                'count': len(users_data),
                'users': users_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"❌ [SuperAdmin] Error listing users: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'message': f'Error al listar usuarios: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def retrieve(self, request, pk=None):
        """
        🔍 Obtener detalles de un usuario específico
        
        GET /api/v1/superadmin/users/{id}/
        """
        try:
            user = User.objects.annotate(
                orders_count=Count('orders', distinct=True),
                total_spent=Sum('orders__total', filter=Q(orders__status='paid'))
            ).select_related('profile').get(pk=pk)
            
            # Obtener órdenes recientes
            recent_orders = Order.objects.filter(
                user=user
            ).select_related('event').order_by('-created_at')[:10]
            
            orders_data = [{
                'id': order.id,
                'order_number': order.order_number,
                'event_title': order.event.title if order.event else 'N/A',
                'total': float(order.total),
                'status': order.status,
                'created_at': order.created_at.isoformat(),
            } for order in recent_orders]
            
            # Obtener datos del profile de forma segura
            profile_city = None
            profile_country = None
            try:
                if hasattr(user, 'profile') and user.profile:
                    profile_city = user.profile.city
                    profile_country = user.profile.country
            except Exception:
                pass  # Profile no existe, dejar como None
            
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.get_full_name(),
                'phone_number': user.phone_number or '',
                'is_active': user.is_active,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
                'is_organizer': user.is_organizer,
                'is_validator': user.is_validator,
                'is_guest': user.is_guest,
                'date_joined': user.date_joined.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None,
                'profile_completed_at': user.profile_completed_at.isoformat() if user.profile_completed_at else None,
                'orders_count': user.orders_count or 0,
                'total_spent': float(user.total_spent or 0),
                'recent_orders': orders_data,
                'profile_picture': user.profile_picture.url if user.profile_picture else None,
                'city': profile_city,
                'country': profile_country,
            }
            
            return Response({
                'success': True,
                'user': user_data
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Usuario no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"❌ [SuperAdmin] Error retrieving user {pk}: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error al obtener usuario: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def destroy(self, request, pk=None):
        """
        🗑️ Eliminar usuario de forma robusta con cascada
        
        DELETE /api/v1/superadmin/users/{id}/
        
        Elimina todas las referencias del usuario en:
        - OTP y OTP attempts
        - Tokens de autenticación
        - Perfil
        - Emails y cuentas sociales
        - Organizadores
        - Órdenes (las conserva pero desvincula)
        - Tickets (actualiza referencias a NULL)
        - Validaciones
        - Pagos guardados
        - Sincronizaciones WooCommerce
        - Eventos visualizados y conversiones
        """
        try:
            user = User.objects.get(pk=pk)
            user_email = user.email
            
            logger.info(f"🗑️ [SuperAdmin] Iniciando eliminación de usuario: {user_email} (ID: {pk})")
            
            with transaction.atomic():
                # 1. OTP y OTP Attempts
                otp_attempts = OTPAttempt.objects.filter(otp__user=user)
                otp_attempts_count = otp_attempts.count()
                otp_attempts.delete()
                logger.info(f"  ✓ Eliminados {otp_attempts_count} OTP attempts")
                
                otps = OTP.objects.filter(user=user)
                otps_count = otps.count()
                otps.delete()
                logger.info(f"  ✓ Eliminados {otps_count} OTPs")
                
                # 2. Tokens JWT blacklist
                blacklisted_tokens = BlacklistedToken.objects.filter(
                    token__user=user
                )
                blacklisted_count = blacklisted_tokens.count()
                blacklisted_tokens.delete()
                logger.info(f"  ✓ Eliminados {blacklisted_count} tokens en blacklist")
                
                outstanding_tokens = OutstandingToken.objects.filter(user=user)
                outstanding_count = outstanding_tokens.count()
                outstanding_tokens.delete()
                logger.info(f"  ✓ Eliminados {outstanding_count} outstanding tokens")
                
                # 3. Auth tokens
                Token.objects.filter(user=user).delete()
                logger.info(f"  ✓ Eliminados auth tokens")
                
                # 4. Grupos y permisos
                user.groups.clear()
                user.user_permissions.clear()
                logger.info(f"  ✓ Limpiados grupos y permisos")
                
                # 5. Perfil
                if hasattr(user, 'profile'):
                    user.profile.delete()
                    logger.info(f"  ✓ Eliminado perfil")
                
                # 6. Emails y cuentas sociales
                EmailAddress.objects.filter(user=user).delete()
                SocialAccount.objects.filter(user=user).delete()
                logger.info(f"  ✓ Eliminadas cuentas de email y sociales")
                
                # 7. Organizadores
                OrganizerUser.objects.filter(user=user).delete()
                logger.info(f"  ✓ Eliminadas relaciones con organizadores")
                
                # 8. Formularios creados
                Form.objects.filter(created_by=user).delete()
                logger.info(f"  ✓ Eliminados formularios creados")
                
                # 9. Tickets - Actualizar referencias a NULL en lugar de eliminar
                Ticket.objects.filter(approved_by=user).update(approved_by=None)
                Ticket.objects.filter(check_in_by=user).update(check_in_by=None)
                logger.info(f"  ✓ Actualizadas referencias en tickets")
                
                # 10. Notas de tickets
                TicketNote.objects.filter(author=user).delete()
                logger.info(f"  ✓ Eliminadas notas de tickets")
                
                # 11. Órdenes - NO eliminar, solo desvincular (para mantener historial)
                orders_count = Order.objects.filter(user=user).count()
                # Las órdenes se mantienen con el email pero sin user_id
                # Esto se manejará automáticamente con on_delete=SET_NULL si está configurado
                logger.info(f"  ℹ️  {orders_count} órdenes quedan en el sistema (desvinculadas)")
                
                # 12. Validaciones
                ValidatorSession.objects.filter(user=user).delete()
                ValidationTicketNote.objects.filter(user=user).delete()
                logger.info(f"  ✓ Eliminadas sesiones de validación")
                
                # 13. Pagos guardados
                SavedCard.objects.filter(user=user).delete()
                logger.info(f"  ✓ Eliminadas tarjetas guardadas")
                
                # 14. Sincronizaciones WooCommerce
                SyncConfiguration.objects.filter(created_by=user).delete()
                SyncExecution.objects.filter(triggered_by=user).delete()
                logger.info(f"  ✓ Eliminadas configuraciones de sincronización")
                
                # 15. Analytics de eventos
                EventView.objects.filter(user=user).delete()
                ConversionFunnel.objects.filter(user=user).delete()
                logger.info(f"  ✓ Eliminados datos de analytics")
                
                # 16. Finalmente eliminar el usuario
                user.delete()
                logger.info(f"  ✓ Usuario eliminado")
            
            logger.info(f"✅ [SuperAdmin] Usuario {user_email} (ID: {pk}) eliminado exitosamente")
            
            return Response({
                'success': True,
                'message': f'Usuario {user_email} eliminado exitosamente con todas sus referencias'
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Usuario no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"❌ [SuperAdmin] Error eliminando usuario {pk}: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'message': f'Error al eliminar usuario: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        """
        🚫 Suspender usuario
        
        POST /api/v1/superadmin/users/{id}/suspend/
        """
        try:
            user = User.objects.get(pk=pk)
            user.is_active = False
            user.save(update_fields=['is_active'])
            
            logger.info(f"✅ [SuperAdmin] Usuario {user.email} suspendido")
            
            return Response({
                'success': True,
                'message': f'Usuario {user.email} suspendido exitosamente'
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Usuario no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"❌ [SuperAdmin] Error suspendiendo usuario {pk}: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error al suspender usuario: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        ✅ Activar usuario
        
        POST /api/v1/superadmin/users/{id}/activate/
        """
        try:
            user = User.objects.get(pk=pk)
            user.is_active = True
            user.save(update_fields=['is_active'])
            
            logger.info(f"✅ [SuperAdmin] Usuario {user.email} activado")
            
            return Response({
                'success': True,
                'message': f'Usuario {user.email} activado exitosamente'
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Usuario no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"❌ [SuperAdmin] Error activando usuario {pk}: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error al activar usuario: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def change_password(self, request, pk=None):
        """
        🔑 Cambiar contraseña de usuario
        
        POST /api/v1/superadmin/users/{id}/change_password/
        Body: { "new_password": "nueva_contraseña" }
        """
        try:
            user = User.objects.get(pk=pk)
            new_password = request.data.get('new_password')
            
            if not new_password:
                return Response({
                    'success': False,
                    'message': 'Nueva contraseña requerida'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if len(new_password) < 8:
                return Response({
                    'success': False,
                    'message': 'La contraseña debe tener al menos 8 caracteres'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(new_password)
            user.last_password_change = timezone.now()
            user.save(update_fields=['password', 'last_password_change'])
            
            logger.info(f"✅ [SuperAdmin] Contraseña cambiada para usuario {user.email}")
            
            return Response({
                'success': True,
                'message': f'Contraseña cambiada exitosamente para {user.email}'
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Usuario no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"❌ [SuperAdmin] Error cambiando contraseña para usuario {pk}: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error al cambiar contraseña: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def impersonate(self, request, pk=None):
        """
        👤 Generar token para impersonar usuario
        
        POST /api/v1/superadmin/users/{id}/impersonate/
        
        Returns:
            access_token y refresh_token para acceder como el usuario
        """
        try:
            user = User.objects.get(pk=pk)
            
            if not user.is_active:
                return Response({
                    'success': False,
                    'message': 'No se puede impersonar un usuario inactivo'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Generar tokens JWT
            refresh = RefreshToken.for_user(user)
            
            logger.info(f"✅ [SuperAdmin] Token de impersonación generado para usuario {user.email}")
            
            return Response({
                'success': True,
                'message': f'Token generado para impersonar a {user.email}',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'full_name': user.get_full_name()
                },
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                }
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Usuario no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"❌ [SuperAdmin] Error generando token de impersonación para usuario {pk}: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error al generar token: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])  # TODO: Cambiar a [IsAdminUser] en producción
def superadmin_stats(request):
    """
    📊 Estadísticas generales del Super Admin
    
    GET /api/v1/superadmin/stats/
    """
    try:
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        organizers = User.objects.filter(is_organizer=True).count()
        guests = User.objects.filter(is_guest=True).count()
        
        total_orders = Order.objects.filter(status='paid').count()
        total_revenue = Order.objects.filter(status='paid').aggregate(
            total=Sum('total')
        )['total'] or 0
        
        recent_users = User.objects.order_by('-date_joined')[:5]
        recent_users_data = [{
            'id': user.id,
            'email': user.email,
            'full_name': user.get_full_name(),
            'date_joined': user.date_joined.isoformat()
        } for user in recent_users]
        
        return Response({
            'success': True,
            'stats': {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': total_users - active_users,
                'organizers': organizers,
                'guests': guests,
                'total_orders': total_orders,
                'total_revenue': float(total_revenue),
                'recent_users': recent_users_data
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting stats: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error al obtener estadísticas: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])  # TODO: Cambiar a [IsAdminUser] en producción
def sales_analytics(request):
    """
    💰 Analytics de ventas de la plataforma
    
    GET /api/v1/superadmin/sales-analytics/
    
    Returns:
        - Ventas efectivas totales (sumatoria de subtotales pagados)
        - Cargos pagados totales (sumatoria de service_fee pagados)
        - Ventas por tipo de producto (eventos, experiencias, alojamientos)
        - Número de órdenes pagadas
        - Ticket promedio
    """
    try:
        from apps.events.models import Event
        from apps.organizers.models import Organizer
        
        # Obtener todas las órdenes pagadas
        paid_orders = Order.objects.filter(status='paid')
        
        # Calcular ventas efectivas (sumatoria de subtotales)
        total_sales = paid_orders.aggregate(total=Sum('subtotal'))['total'] or 0
        
        # Calcular cargos pagados (sumatoria de service_fee)
        total_service_fees = paid_orders.aggregate(total=Sum('service_fee'))['total'] or 0
        
        # Número de órdenes pagadas
        paid_orders_count = paid_orders.count()
        
        # Ticket promedio (incluyendo service fee)
        average_order_value = paid_orders.aggregate(avg=Sum('total'))['avg'] or 0
        if paid_orders_count > 0:
            average_order_value = average_order_value / paid_orders_count
        
        # Ventas por tipo de producto
        # Por ahora solo eventos están habilitados
        event_sales = total_sales  # TODO: filtrar por tipo cuando se agreguen experiencias y alojamientos
        event_fees = total_service_fees
        
        # Top 5 eventos por ventas
        top_events = []
        events_sales_data = paid_orders.values('event').annotate(
            total_sales=Sum('subtotal'),
            total_fees=Sum('service_fee'),
            orders_count=Count('id')
        ).order_by('-total_sales')[:5]
        
        for event_data in events_sales_data:
            try:
                event = Event.objects.get(id=event_data['event'])
                top_events.append({
                    'event_id': str(event.id),
                    'event_title': event.title,
                    'organizer_name': event.organizer.name if event.organizer else 'N/A',
                    'total_sales': float(event_data['total_sales'] or 0),
                    'total_fees': float(event_data['total_fees'] or 0),
                    'orders_count': event_data['orders_count']
                })
            except Event.DoesNotExist:
                continue
        
        logger.info(f"✅ [SuperAdmin] Sales analytics calculated: ${total_sales} in sales, ${total_service_fees} in fees")
        
        return Response({
            'success': True,
            'analytics': {
                # Ventas efectivas (lo que va a organizadores)
                'total_sales': float(total_sales),
                # Cargos pagados (lo que va a la plataforma)
                'total_service_fees': float(total_service_fees),
                # Total bruto (ventas + cargos)
                'gross_total': float(total_sales + total_service_fees),
                # Estadísticas
                'paid_orders_count': paid_orders_count,
                'average_order_value': float(average_order_value),
                # Ventas por tipo (por ahora solo eventos)
                'by_type': {
                    'events': {
                        'sales': float(event_sales),
                        'fees': float(event_fees),
                        'percentage': 100.0  # Por ahora 100% es eventos
                    },
                    'experiences': {
                        'sales': 0.0,
                        'fees': 0.0,
                        'percentage': 0.0
                    },
                    'accommodations': {
                        'sales': 0.0,
                        'fees': 0.0,
                        'percentage': 0.0
                    }
                },
                # Top eventos
                'top_events': top_events
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting sales analytics: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al obtener analytics de ventas: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])  # TODO: Cambiar a [IsAdminUser] en producción
def events_analytics(request):
    """
    📅 Analytics de eventos de la plataforma
    
    GET /api/v1/superadmin/events-analytics/
    
    Query Params:
        - organizer_id (optional): Filtrar por organizador específico
        - status (optional): Filtrar por estado (published, draft, cancelled, etc.)
    
    Returns:
        Lista de eventos con sus estadísticas de ventas
    """
    try:
        from apps.events.models import Event
        from django.db.models import Sum, Count, Q
        
        organizer_id = request.query_params.get('organizer_id')
        status_filter = request.query_params.get('status')
        
        # Base queryset de eventos
        events_qs = Event.objects.select_related('organizer', 'location').all()
        
        if organizer_id:
            events_qs = events_qs.filter(organizer_id=organizer_id)
        
        if status_filter:
            events_qs = events_qs.filter(status=status_filter)
        
        # Calcular estadísticas por evento
        events_data = []
        
        for event in events_qs:
            # Obtener órdenes pagadas de este evento
            paid_orders = Order.objects.filter(
                event=event,
                status='paid'
            )
            
            # Calcular totales
            sales_data = paid_orders.aggregate(
                total_sales=Sum('subtotal'),
                total_fees=Sum('service_fee'),
                total_amount=Sum('total'),
                orders_count=Count('id')
            )
            
            # Calcular tickets vendidos
            from apps.events.models import OrderItem
            tickets_sold = OrderItem.objects.filter(
                order__event=event,
                order__status='paid'
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            # Calcular tasa de comisión efectiva
            total_sales = float(sales_data['total_sales'] or 0)
            total_fees = float(sales_data['total_fees'] or 0)
            effective_fee_rate = 0
            if total_sales > 0:
                effective_fee_rate = (total_fees / total_sales) * 100
            
            events_data.append({
                'id': str(event.id),
                'title': event.title,
                'slug': event.slug,
                'status': event.status,
                'organizer_id': str(event.organizer.id),
                'organizer_name': event.organizer.name,
                'start_date': event.start_date.isoformat() if event.start_date else None,
                'end_date': event.end_date.isoformat() if event.end_date else None,
                'location': event.location.name if event.location else 'Sin ubicación',
                'location_address': event.location.address if event.location else '',
                'pricing_mode': event.pricing_mode,
                'is_free': event.is_free,
                # Estadísticas de ventas
                'total_sales': total_sales,
                'total_service_fees': total_fees,
                'gross_total': float(sales_data['total_amount'] or 0),
                'tickets_sold': tickets_sold,
                'orders_count': sales_data['orders_count'] or 0,
                'effective_fee_rate': round(effective_fee_rate, 2),
                'configured_fee_rate': float(event.service_fee_rate * 100) if event.service_fee_rate else (float(event.organizer.default_service_fee_rate * 100) if event.organizer.default_service_fee_rate else 0),
                # Metadatos
                'created_at': event.created_at.isoformat(),
                'updated_at': event.updated_at.isoformat(),
            })
        
        # Ordenar por ventas totales descendente
        events_data.sort(key=lambda x: x['total_sales'], reverse=True)
        
        logger.info(f"✅ [SuperAdmin] Events analytics calculated for {len(events_data)} events")
        
        return Response({
            'success': True,
            'count': len(events_data),
            'events': events_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting events analytics: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al obtener analytics de eventos: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])  # TODO: Cambiar a [IsAdminUser] en producción
def organizer_sales(request):
    """
    📊 Ventas por organizador
    
    GET /api/v1/superadmin/organizer-sales/
    
    Query Params:
        - organizer_id (optional): Filtrar por organizador específico
    
    Returns:
        Lista de organizadores con sus ventas y comisiones generadas
    """
    try:
        from apps.organizers.models import Organizer
        from django.db.models import Sum, Count, F, DecimalField
        
        organizer_id = request.query_params.get('organizer_id')
        
        # Base queryset de organizadores
        organizers_qs = Organizer.objects.all()
        
        if organizer_id:
            organizers_qs = organizers_qs.filter(id=organizer_id)
        
        # Calcular ventas por organizador
        organizers_data = []
        
        for organizer in organizers_qs:
            # Obtener todas las órdenes pagadas de eventos de este organizador
            paid_orders = Order.objects.filter(
                event__organizer=organizer,
                status='paid'
            )
            
            # Calcular totales
            sales_data = paid_orders.aggregate(
                total_sales=Sum('subtotal'),
                total_fees=Sum('service_fee'),
                orders_count=Count('id')
            )
            
            total_sales = float(sales_data['total_sales'] or 0)
            total_fees = float(sales_data['total_fees'] or 0)
            orders_count = sales_data['orders_count'] or 0
            
            # Calcular tasa de comisión promedio
            avg_fee_percentage = 0
            if total_sales > 0:
                avg_fee_percentage = (total_fees / total_sales) * 100
            
            organizers_data.append({
                'organizer_id': str(organizer.id),
                'organizer_name': organizer.name,
                'organizer_email': organizer.contact_email,
                'total_sales': total_sales,
                'total_service_fees': total_fees,
                'gross_total': total_sales + total_fees,
                'orders_count': orders_count,
                'average_fee_percentage': round(avg_fee_percentage, 2),
                'default_service_fee_rate': float(organizer.default_service_fee_rate or 0),
                'status': organizer.status
            })
        
        # Ordenar por ventas totales descendente
        organizers_data.sort(key=lambda x: x['total_sales'], reverse=True)
        
        logger.info(f"✅ [SuperAdmin] Organizer sales calculated for {len(organizers_data)} organizers")
        
        return Response({
            'success': True,
            'count': len(organizers_data),
            'organizers': organizers_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting organizer sales: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al obtener ventas por organizador: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([AllowAny])  # TODO: Cambiar a IsAdminUser en producción
def update_organizer_template(request, organizer_id):
    """
    🚀 ENTERPRISE: Update experience dashboard template for an organizer.
    
    PATCH /api/v1/superadmin/organizers/{id}/template/
    
    Body:
        {
            "experience_dashboard_template": "free_tours" | "standard"
        }
    """
    try:
        from apps.organizers.models import Organizer
        
        organizer = Organizer.objects.get(id=organizer_id)
        template = request.data.get('experience_dashboard_template')
        
        if template not in ['standard', 'free_tours']:
            return Response({
                'success': False,
                'message': 'Template must be "standard" or "free_tours"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Only allow if organizer has experience module
        if not organizer.has_experience_module:
            return Response({
                'success': False,
                'message': 'Organizer does not have experience module enabled'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        organizer.experience_dashboard_template = template
        organizer.save()
        
        logger.info(f"✅ [SuperAdmin] Updated template for organizer {organizer_id}: {template}")
        
        return Response({
            'success': True,
            'message': 'Template updated successfully',
            'organizer': {
                'id': str(organizer.id),
                'name': organizer.name,
                'experience_dashboard_template': organizer.experience_dashboard_template
            }
        }, status=status.HTTP_200_OK)
        
    except Organizer.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Organizer not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error updating template: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error updating template: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🚀 ENTERPRISE: Platform Flow Monitoring Endpoints

@api_view(['GET'])
@permission_classes([AllowAny])  # TODO: Cambiar a IsAdminUser en producción
def ticket_delivery_funnel(request):
    """
    Get ticket delivery funnel metrics.
    
    Returns counts and conversion rates for:
    - Paid orders
    - Emails enqueued
    - Emails sent
    - Emails failed
    """
    try:
        from core.models import PlatformFlow, PlatformFlowEvent, CeleryTaskLog
        from django.db.models import Count, Q
        from datetime import timedelta
        
        # Get date range from query params
        days = int(request.GET.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        # Get flow type filter
        flow_type = request.GET.get('flow_type', 'ticket_checkout')
        
        # Count paid orders
        paid_orders = Order.objects.filter(
            status='paid',
            created_at__gte=start_date
        ).count()
        
        # Count flows
        flows = PlatformFlow.objects.filter(
            flow_type=flow_type,
            created_at__gte=start_date
        )
        
        total_flows = flows.count()
        completed_flows = flows.filter(status='completed').count()
        failed_flows = flows.filter(status='failed').count()
        in_progress_flows = flows.filter(status='in_progress').count()
        
        # Count email events
        email_enqueued = PlatformFlowEvent.objects.filter(
            flow__created_at__gte=start_date,
            step='EMAIL_TASK_ENQUEUED'
        ).count()
        
        email_sent = PlatformFlowEvent.objects.filter(
            flow__created_at__gte=start_date,
            step='EMAIL_SENT',
            status='success'
        ).count()
        
        email_failed = PlatformFlowEvent.objects.filter(
            flow__created_at__gte=start_date,
            step='EMAIL_FAILED',
            status='failure'
        ).count()
        
        # Calculate conversion rates
        enqueue_rate = (email_enqueued / paid_orders * 100) if paid_orders > 0 else 0
        success_rate = (email_sent / email_enqueued * 100) if email_enqueued > 0 else 0
        failure_rate = (email_failed / email_enqueued * 100) if email_enqueued > 0 else 0
        completion_rate = (completed_flows / total_flows * 100) if total_flows > 0 else 0
        
        return Response({
            'success': True,
            'period': {
                'days': days,
                'start_date': start_date.isoformat(),
                'end_date': timezone.now().isoformat()
            },
            'funnel': {
                'paid_orders': paid_orders,
                'emails_enqueued': email_enqueued,
                'emails_sent': email_sent,
                'emails_failed': email_failed,
                'enqueue_rate': round(enqueue_rate, 2),
                'success_rate': round(success_rate, 2),
                'failure_rate': round(failure_rate, 2)
            },
            'flows': {
                'total': total_flows,
                'completed': completed_flows,
                'failed': failed_flows,
                'in_progress': in_progress_flows,
                'completion_rate': round(completion_rate, 2)
            }
        })
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting funnel: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting funnel: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def ticket_delivery_issues(request):
    """
    Get list of flows with delivery issues.
    
    Returns flows that:
    - Failed
    - Have email failures
    - Are stuck in progress for too long
    """
    try:
        from core.models import PlatformFlow, PlatformFlowEvent
        from datetime import timedelta
        
        # Get filters
        days = int(request.GET.get('days', 7))
        limit = int(request.GET.get('limit', 20))
        start_date = timezone.now() - timedelta(days=days)
        
        # Get failed flows
        failed_flows = PlatformFlow.objects.filter(
            status='failed',
            created_at__gte=start_date
        ).select_related('user', 'organizer', 'primary_order', 'event').order_by('-created_at')[:limit]
        
        # Get flows with email failures
        flows_with_email_failures = PlatformFlow.objects.filter(
            created_at__gte=start_date,
            events__step='EMAIL_FAILED'
        ).distinct().select_related('user', 'organizer', 'primary_order', 'event').order_by('-created_at')[:limit]
        
        # Get stuck flows (in progress for more than 1 hour)
        stuck_threshold = timezone.now() - timedelta(hours=1)
        stuck_flows = PlatformFlow.objects.filter(
            status='in_progress',
            created_at__lt=stuck_threshold
        ).select_related('user', 'organizer', 'primary_order', 'event').order_by('-created_at')[:limit]
        
        def serialize_flow(flow):
            # Get last event
            last_event = flow.events.order_by('-created_at').first()
            
            # Get email logs
            email_events = flow.events.filter(
                step__in=['EMAIL_TASK_ENQUEUED', 'EMAIL_SENT', 'EMAIL_FAILED']
            ).order_by('-created_at')
            
            return {
                'id': str(flow.id),
                'flow_type': flow.flow_type,
                'status': flow.status,
                'created_at': flow.created_at.isoformat(),
                'completed_at': flow.completed_at.isoformat() if flow.completed_at else None,
                'failed_at': flow.failed_at.isoformat() if flow.failed_at else None,
                'user': {
                    'id': str(flow.user.id) if flow.user else None,
                    'email': flow.user.email if flow.user else None
                } if flow.user else None,
                'organizer': {
                    'id': str(flow.organizer.id) if flow.organizer else None,
                    'name': flow.organizer.name if flow.organizer else None
                } if flow.organizer else None,
                'order': {
                    'id': str(flow.primary_order.id) if flow.primary_order else None,
                    'order_number': flow.primary_order.order_number if flow.primary_order else None,
                    'total': float(flow.primary_order.total) if flow.primary_order else None
                } if flow.primary_order else None,
                'event': {
                    'id': str(flow.event.id) if flow.event else None,
                    'title': flow.event.title if flow.event else None
                } if flow.event else None,
                'last_event': {
                    'step': last_event.step,
                    'status': last_event.status,
                    'message': last_event.message,
                    'created_at': last_event.created_at.isoformat()
                } if last_event else None,
                'email_status': {
                    'enqueued': email_events.filter(step='EMAIL_TASK_ENQUEUED').exists(),
                    'sent': email_events.filter(step='EMAIL_SENT').exists(),
                    'failed': email_events.filter(step='EMAIL_FAILED').exists(),
                    'last_attempt': email_events.first().created_at.isoformat() if email_events.exists() else None
                }
            }
        
        return Response({
            'success': True,
            'issues': {
                'failed_flows': [serialize_flow(f) for f in failed_flows],
                'email_failures': [serialize_flow(f) for f in flows_with_email_failures],
                'stuck_flows': [serialize_flow(f) for f in stuck_flows]
            },
            'counts': {
                'failed': failed_flows.count(),
                'email_failures': flows_with_email_failures.count(),
                'stuck': stuck_flows.count()
            }
        })
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting issues: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting issues: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def all_flows(request):
    """
    🚀 ENTERPRISE: Get ALL platform flows with filters and pagination.
    
    Query params:
    - days: Number of days to look back (default: 7)
    - status: Filter by status (completed, failed, in_progress, etc.)
    - flow_type: Filter by flow type (ticket_checkout, etc.)
    - search: Search by order_number, email, event title
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    """
    try:
        from core.models import PlatformFlow
        from django.db.models import Q
        
        logger.info("📊 [SuperAdmin] Getting all flows")
        
        # Get query parameters
        days = int(request.GET.get('days', 7))
        status_filter = request.GET.get('status', '')
        flow_type_filter = request.GET.get('flow_type', '')
        search = request.GET.get('search', '')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 20)), 100)
        
        # Calculate date range
        start_date = timezone.now() - timedelta(days=days)
        
        # Base queryset
        queryset = PlatformFlow.objects.filter(
            created_at__gte=start_date
        ).select_related('user', 'organizer', 'primary_order', 'event')
        
        # Apply filters
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if flow_type_filter:
            queryset = queryset.filter(flow_type=flow_type_filter)
        
        # Apply search
        if search:
            queryset = queryset.filter(
                Q(primary_order__order_number__icontains=search) |
                Q(primary_order__email__icontains=search) |
                Q(user__email__icontains=search) |
                Q(event__title__icontains=search)
            )
        
        # Order by most recent
        queryset = queryset.order_by('-created_at')
        
        # Get total count
        total_count = queryset.count()
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        flows = queryset[start_idx:end_idx]
        
        # Serialize flows
        def serialize_flow(flow):
            # Get last event
            last_event = flow.events.order_by('-created_at').first()
            
            # Get email events
            email_events = flow.events.filter(
                step__in=['EMAIL_TASK_ENQUEUED', 'EMAIL_SENT', 'EMAIL_FAILED']
            ).order_by('-created_at')
            
            # Calculate duration
            duration = None
            if flow.completed_at and flow.created_at:
                duration_delta = flow.completed_at - flow.created_at
                duration = str(duration_delta)
            elif flow.failed_at and flow.created_at:
                duration_delta = flow.failed_at - flow.created_at
                duration = str(duration_delta)
            
            return {
                'id': str(flow.id),
                'flow_type': flow.flow_type,
                'status': flow.status,
                'created_at': flow.created_at.isoformat(),
                'completed_at': flow.completed_at.isoformat() if flow.completed_at else None,
                'failed_at': flow.failed_at.isoformat() if flow.failed_at else None,
                'duration': duration,
                'user': {
                    'id': str(flow.user.id) if flow.user else None,
                    'email': flow.user.email if flow.user else None
                } if flow.user else None,
                'organizer': {
                    'id': str(flow.organizer.id) if flow.organizer else None,
                    'name': flow.organizer.name if flow.organizer else None
                } if flow.organizer else None,
                'order': {
                    'id': str(flow.primary_order.id) if flow.primary_order else None,
                    'order_number': flow.primary_order.order_number if flow.primary_order else None,
                    'total': float(flow.primary_order.total) if flow.primary_order else None,
                    'email': flow.primary_order.email if flow.primary_order else None
                } if flow.primary_order else None,
                'event': {
                    'id': str(flow.event.id) if flow.event else None,
                    'title': flow.event.title if flow.event else None
                } if flow.event else None,
                'last_event': {
                    'step': last_event.step,
                    'status': last_event.status,
                    'message': last_event.message,
                    'created_at': last_event.created_at.isoformat()
                } if last_event else None,
                'email_status': {
                    'enqueued': email_events.filter(step='EMAIL_TASK_ENQUEUED').exists(),
                    'sent': email_events.filter(step='EMAIL_SENT').exists(),
                    'failed': email_events.filter(step='EMAIL_FAILED').exists(),
                    'last_attempt': email_events.first().created_at.isoformat() if email_events.exists() else None
                }
            }
        
        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size
        has_next = page < total_pages
        has_prev = page > 1
        
        logger.info(f"✅ [SuperAdmin] Found {total_count} flows (page {page}/{total_pages})")
        
        return Response({
            'success': True,
            'flows': [serialize_flow(f) for f in flows],
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev
            },
            'filters': {
                'days': days,
                'status': status_filter,
                'flow_type': flow_type_filter,
                'search': search
            }
        })
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting all flows: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting flows: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def flow_detail(request, flow_id):
    """
    Get detailed information about a specific flow.
    
    Returns:
    - Flow information
    - All events in timeline
    - Related Celery tasks
    - Related email logs
    """
    try:
        from core.models import PlatformFlow, CeleryTaskLog
        from apps.events.models import EmailLog
        
        flow = PlatformFlow.objects.select_related(
            'user', 'organizer', 'primary_order', 'event', 'experience'
        ).get(id=flow_id)
        
        # Get all events
        events = flow.events.select_related(
            'order', 'payment', 'email_log', 'celery_task_log'
        ).order_by('created_at')
        
        # Get Celery logs
        celery_logs = CeleryTaskLog.objects.filter(flow=flow).order_by('created_at')
        
        # Get email logs if order exists
        email_logs = []
        if flow.primary_order:
            email_logs = EmailLog.objects.filter(order=flow.primary_order).order_by('created_at')
        
        return Response({
            'success': True,
            'flow': {
                'id': str(flow.id),
                'flow_type': flow.flow_type,
                'status': flow.status,
                'created_at': flow.created_at.isoformat(),
                'completed_at': flow.completed_at.isoformat() if flow.completed_at else None,
                'failed_at': flow.failed_at.isoformat() if flow.failed_at else None,
                'metadata': flow.metadata,
                'user': {
                    'id': str(flow.user.id) if flow.user else None,
                    'email': flow.user.email if flow.user else None,
                    'name': f"{flow.user.first_name} {flow.user.last_name}" if flow.user else None
                } if flow.user else None,
                'organizer': {
                    'id': str(flow.organizer.id) if flow.organizer else None,
                    'name': flow.organizer.name if flow.organizer else None
                } if flow.organizer else None,
                'order': {
                    'id': str(flow.primary_order.id) if flow.primary_order else None,
                    'order_number': flow.primary_order.order_number if flow.primary_order else None,
                    'status': flow.primary_order.status if flow.primary_order else None,
                    'total': float(flow.primary_order.total) if flow.primary_order else None,
                    'email': flow.primary_order.email if flow.primary_order else None
                } if flow.primary_order else None,
                'event': {
                    'id': str(flow.event.id) if flow.event else None,
                    'title': flow.event.title if flow.event else None
                } if flow.event else None
            },
            'events': [{
                'id': str(e.id),
                'step': e.step,
                'status': e.status,
                'source': e.source,
                'message': e.message,
                'created_at': e.created_at.isoformat(),
                'metadata': e.metadata,
                'order_id': str(e.order.id) if e.order else None,
                'payment_id': str(e.payment.id) if e.payment else None,
                'email_log_id': str(e.email_log.id) if e.email_log else None,
                'celery_task_log_id': str(e.celery_task_log.id) if e.celery_task_log else None
            } for e in events],
            'celery_logs': [{
                'id': str(log.id),
                'task_id': log.task_id,
                'task_name': log.task_name,
                'status': log.status,
                'queue': log.queue,
                'created_at': log.created_at.isoformat(),
                'duration_ms': log.duration_ms,
                'error': log.error,
                'args': log.args,
                'kwargs': log.kwargs
            } for log in celery_logs],
            'email_logs': [{
                'id': str(log.id),
                'to_email': log.to_email,
                'subject': log.subject,
                'template': log.template,
                'status': log.status,
                'attempts': log.attempts,
                'error': log.error,
                'sent_at': log.sent_at.isoformat() if log.sent_at else None,
                'created_at': log.created_at.isoformat()
            } for log in email_logs]
        })
        
    except PlatformFlow.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Flow not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting flow detail: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting flow detail: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def celery_tasks_list(request):
    """
    Get list of Celery task logs.
    
    Supports filtering by:
    - task_name
    - status
    - date range
    """
    try:
        from core.models import CeleryTaskLog
        from datetime import timedelta
        
        # Get filters
        task_name = request.GET.get('task_name')
        task_status = request.GET.get('status')
        days = int(request.GET.get('days', 7))
        limit = int(request.GET.get('limit', 50))
        
        start_date = timezone.now() - timedelta(days=days)
        
        # Build query
        query = CeleryTaskLog.objects.filter(created_at__gte=start_date)
        
        if task_name:
            query = query.filter(task_name__icontains=task_name)
        
        if task_status:
            query = query.filter(status=task_status)
        
        # Get logs
        logs = query.select_related('flow', 'order', 'user').order_by('-created_at')[:limit]
        
        # Get counts by status
        status_counts = CeleryTaskLog.objects.filter(
            created_at__gte=start_date
        ).values('status').annotate(count=Count('id'))
        
        return Response({
            'success': True,
            'logs': [{
                'id': str(log.id),
                'task_id': log.task_id,
                'task_name': log.task_name,
                'status': log.status,
                'queue': log.queue,
                'created_at': log.created_at.isoformat(),
                'duration_ms': log.duration_ms,
                'error': log.error[:200] if log.error else None,  # Truncate error
                'flow_id': str(log.flow.id) if log.flow else None,
                'order_id': str(log.order.id) if log.order else None,
                'order_number': log.order.order_number if log.order else None
            } for log in logs],
            'status_counts': {item['status']: item['count'] for item in status_counts},
            'total': query.count()
        })
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting celery tasks: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting celery tasks: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

