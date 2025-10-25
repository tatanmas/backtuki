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

