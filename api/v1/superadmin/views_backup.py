"""
Super Admin Views - Enterprise User Management
Endpoints públicos (temporal) para gestión de usuarios.
TODO: Agregar autenticación y permisos de super admin en producción.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from .permissions import IsSuperUser  # ENTERPRISE: Solo superusers autenticados
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
from core.models import Country
from core.serializers import CountrySerializer
from apps.experiences.models import Experience
from apps.experiences.utils import generate_tour_instances_from_pattern
from .serializers import JsonExperienceCreateSerializer

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
    
    permission_classes = [IsSuperUser]  # ENTERPRISE: Solo superusers
    
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
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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
            
            # 🚀 Calcular service fee efectivo siguiendo jerarquía: Event > Organizer > Platform
            if event.service_fee_rate is not None:
                effective_fee_rate = float(event.service_fee_rate)
                service_fee_source = 'event'
            elif event.organizer.default_service_fee_rate is not None:
                effective_fee_rate = float(event.organizer.default_service_fee_rate)
                service_fee_source = 'organizer'
            else:
                effective_fee_rate = 0.15  # Platform default
                service_fee_source = 'platform'
            
            # Calcular tasa de comisión efectiva (para mostrar en porcentaje)
            total_sales = float(sales_data['total_sales'] or 0)
            total_fees = float(sales_data['total_fees'] or 0)
            effective_fee_percentage = 0
            if total_sales > 0:
                effective_fee_percentage = (total_fees / total_sales) * 100
            
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
                'effective_fee_rate': round(effective_fee_percentage, 2),  # En porcentaje para compatibilidad
                'effective_service_fee_rate': effective_fee_rate,  # En decimal (0.0 a 1.0)
                'service_fee_rate': float(event.service_fee_rate) if event.service_fee_rate is not None else None,  # Fee configurado del evento (puede ser null)
                'service_fee_source': service_fee_source,  # 'event' | 'organizer' | 'platform'
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
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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
            
            # 🚀 Contar productos por tipo
            from apps.events.models import Event
            events_count = Event.objects.filter(organizer=organizer, deleted_at__isnull=True).count()
            
            experiences_count = 0
            if organizer.has_experience_module:
                try:
                    from apps.experiences.models import Experience
                    experiences_count = Experience.objects.filter(organizer=organizer, deleted_at__isnull=True).count()
                except Exception:
                    pass
            
            accommodations_count = 0
            if organizer.has_accommodation_module:
                try:
                    from apps.accommodations.models import Accommodation
                    accommodations_count = Accommodation.objects.filter(organizer=organizer, deleted_at__isnull=True).count()
                except Exception:
                    pass
            
            # 🚀 Service fee efectivo (siguiendo jerarquía)
            effective_service_fee_rate = float(organizer.default_service_fee_rate) if organizer.default_service_fee_rate is not None else 0.15
            service_fee_source = 'organizer' if organizer.default_service_fee_rate is not None else 'platform'
            
            # Normalize legacy template values
            template = organizer.experience_dashboard_template
            if template == 'standard':
                template = 'v0'
            elif template == 'free_tours':
                template = 'principal'
            
            organizers_data.append({
                'organizer_id': str(organizer.id),
                'organizer_name': organizer.name,
                'organizer_email': organizer.contact_email,
                'total_sales': total_sales,
                'total_service_fees': total_fees,
                'gross_total': total_sales + total_fees,
                'orders_count': orders_count,
                'average_fee_percentage': round(avg_fee_percentage, 2),
                # 🚀 Service fee configurado (puede ser null)
                'default_service_fee_rate': float(organizer.default_service_fee_rate) if organizer.default_service_fee_rate is not None else None,
                # 🚀 Service fee efectivo
                'effective_service_fee_rate': effective_service_fee_rate,
                'service_fee_source': service_fee_source,
                'status': organizer.status,
                # 🚀 Módulos activos
                'has_events_module': organizer.has_events_module,
                'has_experience_module': organizer.has_experience_module,
                'has_accommodation_module': organizer.has_accommodation_module,
                # 🚀 Centro de Alumnos
                'is_student_center': organizer.is_student_center,
                # 🚀 Template de dashboard de experiencias (normalizado)
                'experience_dashboard_template': template,
                # 🚀 Conteos de productos
                'events_count': events_count,
                'experiences_count': experiences_count,
                'accommodations_count': accommodations_count,
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
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def update_organizer_template(request, organizer_id):
    """
    🚀 ENTERPRISE: Update experience dashboard template for an organizer.
    
    PATCH /api/v1/superadmin/organizers/{id}/template/
    
    Body:
        {
            "experience_dashboard_template": "principal" | "v0"
        }
    """
    try:
        from apps.organizers.models import Organizer
        
        organizer = Organizer.objects.get(id=organizer_id)
        template = request.data.get('experience_dashboard_template')
        
        if template not in ['v0', 'principal']:
            return Response({
                'success': False,
                'message': 'Template must be "v0" or "principal"'
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



# Temporary file with new endpoints - will be merged into views.py

@api_view(['PATCH'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def update_organizer_modules(request, organizer_id):
    """
    🚀 ENTERPRISE: Update organizer modules (events, experiences, accommodations) and student center flag.
    
    PATCH /api/v1/superadmin/organizers/{id}/modules/
    
    Body:
        {
            "has_events_module": bool,
            "has_experience_module": bool,
            "has_accommodation_module": bool,
            "is_student_center": bool (optional)
        }
    """
    try:
        from apps.organizers.models import Organizer
        
        organizer = Organizer.objects.get(id=organizer_id)
        
        has_events = request.data.get('has_events_module')
        has_experience = request.data.get('has_experience_module')
        has_accommodation = request.data.get('has_accommodation_module')
        is_student_center = request.data.get('is_student_center')
        
        # Validar que al menos un módulo esté activo
        if not (has_events or has_experience or has_accommodation):
            return Response({
                'success': False,
                'message': 'Al menos un módulo debe estar activo'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Actualizar módulos
        if has_events is not None:
            organizer.has_events_module = has_events
        if has_experience is not None:
            organizer.has_experience_module = has_experience
        if has_accommodation is not None:
            organizer.has_accommodation_module = has_accommodation
        if is_student_center is not None:
            organizer.is_student_center = is_student_center
        
        organizer.save()
        
        logger.info(f"✅ [SuperAdmin] Updated modules for organizer {organizer_id}: events={has_events}, experience={has_experience}, accommodation={has_accommodation}, is_student_center={is_student_center}")
        
        return Response({
            'success': True,
            'message': 'Módulos actualizados exitosamente',
            'organizer': {
                'id': str(organizer.id),
                'name': organizer.name,
                'has_events_module': organizer.has_events_module,
                'has_experience_module': organizer.has_experience_module,
                'has_accommodation_module': organizer.has_accommodation_module,
                'is_student_center': organizer.is_student_center,
            }
        }, status=status.HTTP_200_OK)
        
    except Organizer.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Organizer not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error updating modules: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error updating modules: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def update_organizer_service_fee(request, organizer_id):
    """
    🚀 ENTERPRISE: Update organizer service fee rate.
    
    PATCH /api/v1/superadmin/organizers/{id}/service-fee/
    
    Body:
        {
            "default_service_fee_rate": number | null  (0.0 to 1.0, e.g., 0.15 for 15%)
        }
    """
    try:
        from apps.organizers.models import Organizer
        from decimal import Decimal
        
        organizer = Organizer.objects.get(id=organizer_id)
        
        fee_rate = request.data.get('default_service_fee_rate')
        
        # Si es null, eliminar el fee (usar platform default)
        if fee_rate is None:
            organizer.default_service_fee_rate = None
            organizer.save()
            
            logger.info(f"✅ [SuperAdmin] Removed service fee for organizer {organizer_id}, will use platform default")
            
            return Response({
                'success': True,
                'message': 'Service fee eliminado, se usará el default de la plataforma (15%)',
                'organizer': {
                    'id': str(organizer.id),
                    'name': organizer.name,
                    'default_service_fee_rate': None,
                    'effective_service_fee_rate': 0.15,
                    'service_fee_source': 'platform'
                }
            }, status=status.HTTP_200_OK)
        
        # Validar que esté entre 0 y 1
        try:
            fee_rate_decimal = Decimal(str(fee_rate))
            if fee_rate_decimal < 0 or fee_rate_decimal > 1:
                return Response({
                    'success': False,
                    'message': 'El service fee debe estar entre 0 y 1 (0% a 100%)'
                }, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'message': 'Service fee inválido'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        organizer.default_service_fee_rate = fee_rate_decimal
        organizer.save()
        
        logger.info(f"✅ [SuperAdmin] Updated service fee for organizer {organizer_id}: {fee_rate_decimal}")
        
        return Response({
            'success': True,
            'message': 'Service fee actualizado exitosamente',
            'organizer': {
                'id': str(organizer.id),
                'name': organizer.name,
                'default_service_fee_rate': float(fee_rate_decimal),
                'effective_service_fee_rate': float(fee_rate_decimal),
                'service_fee_source': 'organizer'
            }
        }, status=status.HTTP_200_OK)
        
    except Organizer.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Organizer not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error updating service fee: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error updating service fee: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def update_event_service_fee(request, event_id):
    """
    🚀 ENTERPRISE: Update event service fee rate.
    
    PATCH /api/v1/superadmin/events/{id}/service-fee/
    
    Body:
        {
            "service_fee_rate": number | null  (0.0 to 1.0, e.g., 0.15 for 15%)
        }
    """
    try:
        from apps.events.models import Event
        from apps.organizers.models import Organizer
        from decimal import Decimal
        
        event = Event.objects.get(id=event_id)
        
        fee_rate = request.data.get('service_fee_rate')
        
        # Si es null, eliminar el fee (usar organizer o platform default)
        if fee_rate is None:
            event.service_fee_rate = None
            event.save()
            
            # Calcular el fee efectivo después de eliminar
            effective_fee = float(event.organizer.default_service_fee_rate) if event.organizer.default_service_fee_rate is not None else 0.15
            fee_source = 'organizer' if event.organizer.default_service_fee_rate is not None else 'platform'
            
            logger.info(f"✅ [SuperAdmin] Removed service fee for event {event_id}, will use {fee_source} default")
            
            return Response({
                'success': True,
                'message': f'Service fee eliminado, se usará el default del organizador/plataforma ({effective_fee*100:.1f}%)',
                'event': {
                    'id': str(event.id),
                    'title': event.title,
                    'service_fee_rate': None,
                    'effective_service_fee_rate': effective_fee,
                    'service_fee_source': fee_source
                }
            }, status=status.HTTP_200_OK)
        
        # Validar que esté entre 0 y 1
        try:
            fee_rate_decimal = Decimal(str(fee_rate))
            if fee_rate_decimal < 0 or fee_rate_decimal > 1:
                return Response({
                    'success': False,
                    'message': 'El service fee debe estar entre 0 y 1 (0% a 100%)'
                }, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'message': 'Service fee inválido'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        event.service_fee_rate = fee_rate_decimal
        event.save()
        
        logger.info(f"✅ [SuperAdmin] Updated service fee for event {event_id}: {fee_rate_decimal}")
        
        return Response({
            'success': True,
            'message': 'Service fee actualizado exitosamente',
            'event': {
                'id': str(event.id),
                'title': event.title,
                'service_fee_rate': float(fee_rate_decimal),
                'effective_service_fee_rate': float(fee_rate_decimal),
                'service_fee_source': 'event'
            }
        }, status=status.HTTP_200_OK)
        
    except Event.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Event not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error updating event service fee: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error updating event service fee: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 🚀 ENTERPRISE: Platform Flow Monitoring Endpoints

@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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
            
            # Get email events (incluyendo reenvíos manuales)
            email_events = flow.events.filter(
                step__in=['EMAIL_TASK_ENQUEUED', 'EMAIL_SENT', 'EMAIL_FAILED',
                         'EMAIL_MANUAL_RESEND_SUCCESS', 'EMAIL_MANUAL_RESEND', 'EMAIL_MANUAL_RESEND_FAILED']
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
                    'sent': email_events.filter(step__in=['EMAIL_SENT', 'EMAIL_MANUAL_RESEND_SUCCESS']).exists(),
                    'failed': email_events.filter(step__in=['EMAIL_FAILED', 'EMAIL_MANUAL_RESEND_FAILED']).exists(),
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
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def events_list(request):
    """
    🚀 ENTERPRISE: Get list of events for filtering.
    
    Returns:
    - List of events with id and title
    """
    try:
        from apps.events.models import Event
        
        events = Event.objects.filter(
            deleted_at__isnull=True
        ).order_by('-created_at').values('id', 'title')[:100]  # Limit to 100 most recent
        
        return Response({
            'success': True,
            'events': list(events)
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting events list: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting events list: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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
        
        # Base queryset - Prefetch events with order for efficient lookup
        queryset = PlatformFlow.objects.filter(
            created_at__gte=start_date
        ).select_related('user', 'organizer', 'primary_order', 'event').prefetch_related('events__order')
        
        # Apply filters
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if flow_type_filter:
            queryset = queryset.filter(flow_type=flow_type_filter)
        
        # Apply event filter
        event_filter = request.GET.get('event_id', '')
        if event_filter:
            queryset = queryset.filter(event_id=event_filter)
        
        # 🚀 ENTERPRISE: Búsqueda inteligente en múltiples campos relacionados
        if search:
            from apps.events.models import Ticket, Order
            from django.db.models import Value, CharField
            from django.db.models.functions import Concat
            search_term = search.strip()
            search_words = search_term.split()
            
            # Construir Q objects para búsqueda en órdenes
            order_q = Q(order_number__icontains=search_term) | Q(email__icontains=search_term) | Q(phone__icontains=search_term)
            
            # Si hay múltiples palabras, buscar combinación de nombre y apellido
            if len(search_words) >= 2:
                # Buscar "nombre apellido" o "apellido nombre"
                first_word = search_words[0]
                second_word = search_words[1]
                
                # Combinación: first_name contiene primera palabra Y last_name contiene segunda palabra
                order_q |= (Q(first_name__icontains=first_word) & Q(last_name__icontains=second_word))
                # Combinación inversa: first_name contiene segunda palabra Y last_name contiene primera palabra
                order_q |= (Q(first_name__icontains=second_word) & Q(last_name__icontains=first_word))
                
                # También buscar cada palabra individualmente
                for word in search_words:
                    order_q |= Q(first_name__icontains=word) | Q(last_name__icontains=word)
            else:
                # Una sola palabra: buscar en first_name o last_name
                order_q |= Q(first_name__icontains=search_term) | Q(last_name__icontains=search_term)
            
            # Buscar órdenes que coincidan
            matching_order_ids = Order.objects.filter(order_q).values_list('id', flat=True)
            
            # Construir Q objects para búsqueda en tickets (asistentes)
            ticket_q = Q(email__icontains=search_term) | Q(ticket_number__icontains=search_term)
            
            # Si hay múltiples palabras, buscar combinación de nombre y apellido en tickets
            if len(search_words) >= 2:
                first_word = search_words[0]
                second_word = search_words[1]
                
                # Combinación: first_name contiene primera palabra Y last_name contiene segunda palabra
                ticket_q |= (Q(first_name__icontains=first_word) & Q(last_name__icontains=second_word))
                # Combinación inversa
                ticket_q |= (Q(first_name__icontains=second_word) & Q(last_name__icontains=first_word))
                
                # También buscar cada palabra individualmente
                for word in search_words:
                    ticket_q |= Q(first_name__icontains=word) | Q(last_name__icontains=word)
            else:
                # Una sola palabra
                ticket_q |= Q(first_name__icontains=search_term) | Q(last_name__icontains=search_term)
            
            # Buscar tickets que coincidan
            matching_ticket_order_ids = Ticket.objects.filter(ticket_q).values_list('order_item__order_id', flat=True).distinct()
            
            # Combinar todos los IDs de órdenes que coinciden
            all_matching_order_ids = set(list(matching_order_ids) + list(matching_ticket_order_ids))
            
            # Aplicar filtro en el queryset
            queryset = queryset.filter(
                Q(primary_order_id__in=all_matching_order_ids) |
                Q(user__email__icontains=search_term) |
                Q(event__title__icontains=search_term) |
                # También buscar en eventos del flow que tengan order_id
                Q(events__order_id__in=all_matching_order_ids)
            ).distinct()
        
        # Apply email status filter
        email_status_filter = request.GET.get('email_status', '')
        if email_status_filter:
            if email_status_filter == 'sent':
                # Incluir EMAIL_SENT y EMAIL_MANUAL_RESEND_SUCCESS
                queryset = queryset.filter(
                    events__step__in=['EMAIL_SENT', 'EMAIL_MANUAL_RESEND_SUCCESS'],
                    events__status='success'
                ).distinct()
            elif email_status_filter == 'failed':
                queryset = queryset.filter(
                    events__step__in=['EMAIL_FAILED', 'EMAIL_MANUAL_RESEND_FAILED']
                ).distinct()
            elif email_status_filter == 'enqueued':
                queryset = queryset.filter(events__step='EMAIL_TASK_ENQUEUED').distinct()
            elif email_status_filter == 'none':
                # Flows sin ningún evento de email
                queryset = queryset.exclude(
                    events__step__in=['EMAIL_TASK_ENQUEUED', 'EMAIL_SENT', 'EMAIL_FAILED',
                                    'EMAIL_MANUAL_RESEND', 'EMAIL_MANUAL_RESEND_SUCCESS', 'EMAIL_MANUAL_RESEND_FAILED']
                ).distinct()
        
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
            
            # Get email events (incluyendo reenvíos manuales)
            email_events = flow.events.filter(
                step__in=['EMAIL_TASK_ENQUEUED', 'EMAIL_SENT', 'EMAIL_FAILED', 
                         'EMAIL_MANUAL_RESEND_SUCCESS', 'EMAIL_MANUAL_RESEND']
            ).order_by('-created_at')
            
            # 🚀 ENTERPRISE: Buscar orden en primary_order o en eventos si no está en primary_order
            order = flow.primary_order
            if not order:
                # Buscar orden en los eventos del flow (prefetch ya cargado)
                order_event = flow.events.filter(order__isnull=False).select_related('order').first()
                if order_event and order_event.order:
                    order = order_event.order
                    # Actualizar primary_order para futuras consultas (sin bloquear)
                    try:
                        flow.primary_order = order
                        flow.save(update_fields=['primary_order'])
                        logger.info(f"📊 [SUPERADMIN] Found order {order.order_number} in flow {flow.id} events, updated primary_order")
                    except Exception as e:
                        logger.warning(f"⚠️ [SUPERADMIN] Could not update primary_order for flow {flow.id}: {e}")
                else:
                    # Debug: Log cuando no se encuentra orden
                    logger.debug(f"🔍 [SUPERADMIN] Flow {flow.id} has no order in primary_order or events")
            
            # 🚀 ENTERPRISE: Obtener primer asistente (ticket holder) de la orden
            attendee_name = None
            if order:
                try:
                    from apps.events.models import Ticket
                    # Optimizar: usar select_related para evitar N+1 queries
                    first_ticket = Ticket.objects.filter(
                        order_item__order=order
                    ).select_related('order_item').order_by('created_at').first()
                    if first_ticket:
                        attendee_name = f"{first_ticket.first_name} {first_ticket.last_name}".strip()
                except Exception as e:
                    logger.debug(f"🔍 [SUPERADMIN] Could not get attendee for order {order.order_number if order else 'N/A'}: {e}")
            
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
                    'id': str(order.id) if order else None,
                    'order_number': order.order_number if order else None,
                    'total': float(order.total) if order else None,
                    'email': order.email if order else None
                } if order else None,
                'attendee_name': attendee_name,
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
                    'sent': email_events.filter(step__in=['EMAIL_SENT', 'EMAIL_MANUAL_RESEND_SUCCESS']).exists(),
                    'failed': email_events.filter(step__in=['EMAIL_FAILED', 'EMAIL_MANUAL_RESEND_FAILED']).exists(),
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
                'search': search,
                'email_status': email_status_filter
            }
        })
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting all flows: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting flows: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def historical_conversion_rates(request):
    """
    🚀 ENTERPRISE: Get historical conversion rates for all steps.
    
    Query params:
        - from_date: ISO format start date (optional)
        - to_date: ISO format end date (optional)
        - organizer_id: Filter by organizer (optional)
        - event_id: Filter by event (optional)
    
    Returns step-by-step historical conversion rates.
    """
    try:
        from core.conversion_metrics import ConversionMetricsService, TICKET_CHECKOUT_STEPS
        from core.models import PlatformFlowEvent
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone
        
        # Parse date parameters
        from_date = None
        to_date = None
        if request.query_params.get('from_date'):
            from_date = parse_datetime(request.query_params.get('from_date'))
            if from_date and not timezone.is_aware(from_date):
                from_date = timezone.make_aware(from_date)
        
        if request.query_params.get('to_date'):
            to_date = parse_datetime(request.query_params.get('to_date'))
            if to_date and not timezone.is_aware(to_date):
                to_date = timezone.make_aware(to_date)
        
        organizer_id = request.query_params.get('organizer_id')
        event_id = request.query_params.get('event_id')
        
        # Get historical rates
        historical_rates = ConversionMetricsService.get_historical_conversion_rates(
            flow_type='ticket_checkout',
            from_date=from_date,
            to_date=to_date,
            organizer_id=organizer_id,
            event_id=event_id
        )
        
        # Format response with step display names
        step_display_map = dict(PlatformFlowEvent.STEP_CHOICES)
        
        steps_data = []
        for step in TICKET_CHECKOUT_STEPS:
            step_data = historical_rates.get(step, {})
            steps_data.append({
                'step': step,
                'step_display': step_display_map.get(step, step),
                'conversion_rate': step_data.get('conversion_rate', 0.0),
                'conversion_percentage': step_data.get('conversion_percentage', 0.0),
                'reached_count': step_data.get('reached_count', 0),
                'previous_count': step_data.get('previous_count'),
                'previous_step': step_data.get('previous_step')
            })
        
        # Calculate overall average
        overall_avg = sum(s.get('conversion_rate', 0.0) for s in historical_rates.values()) / len(historical_rates) if historical_rates else 0.0
        
        return Response({
            'success': True,
            'steps': steps_data,
            'overall_average': round(overall_avg, 4),
            'overall_average_percentage': round(overall_avg * 100, 2),
            'from_date': from_date.isoformat() if from_date else None,
            'to_date': to_date.isoformat() if to_date else None,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting historical conversion rates: {e}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error getting historical conversion rates: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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
        ).prefetch_related('events__order').get(id=flow_id)
        
        # 🚀 ENTERPRISE: Buscar orden en primary_order o en eventos si no está en primary_order
        order = flow.primary_order
        if not order:
            # Buscar orden en los eventos del flow
            order_event = flow.events.filter(order__isnull=False).select_related('order').first()
            if order_event and order_event.order:
                order = order_event.order
                # Actualizar primary_order para futuras consultas
                try:
                    flow.primary_order = order
                    flow.save(update_fields=['primary_order'])
                    logger.info(f"📊 [SUPERADMIN] Found order {order.order_number} in flow {flow_id} events, updated primary_order")
                except Exception as e:
                    logger.warning(f"⚠️ [SUPERADMIN] Could not update primary_order for flow {flow_id}: {e}")
        
        # Get all events
        events = flow.events.select_related(
            'order', 'payment', 'email_log', 'celery_task_log'
        ).order_by('created_at')
        
        # Get Celery logs
        celery_logs = CeleryTaskLog.objects.filter(flow=flow).order_by('created_at')
        
        # Get email logs if order exists
        email_logs = []
        if order:
            email_logs = EmailLog.objects.filter(order=order).order_by('created_at')
        
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
                    'id': str(order.id) if order else None,
                    'order_number': order.order_number if order else None,
                    'status': order.status if order else None,
                    'total': float(order.total) if order else None,
                    'email': order.email if order else None
                } if order else None,
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


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def resend_order_email(request, flow_id):
    """
    🚀 ENTERPRISE: Reenvía el email de confirmación de orden de forma SÍNCRONA (sin Celery).
    
    Similar a cómo se envían los OTP - instantáneo y directo.
    
    Body (opcional):
    - to_email: Email alternativo para enviar (si no se proporciona, usa el email de la orden)
    
    Returns:
    - success: bool
    - message: str
    - metrics: dict con tiempos de ejecución
    """
    try:
        from core.models import PlatformFlow
        from apps.events.email_sender import send_order_confirmation_email_optimized
        from core.flow_logger import FlowLogger
        
        # Get flow
        flow = PlatformFlow.objects.select_related('primary_order').prefetch_related('events__order').get(id=flow_id)
        
        # Si no hay orden en primary_order, intentar obtenerla de los eventos del flow
        order = flow.primary_order
        if not order:
            # Buscar orden en los eventos del flow
            order_event = flow.events.filter(order__isnull=False).select_related('order').first()
            if order_event and order_event.order:
                order = order_event.order
                logger.info(f"📧 [SUPERADMIN] Found order {order.order_number} in flow events, updating primary_order")
                # Actualizar el flow con la orden encontrada
                flow.primary_order = order
                flow.save(update_fields=['primary_order'])
        
        if not order:
            logger.warning(f"📧 [SUPERADMIN] Flow {flow_id} has no associated order")
            return Response({
                'success': False,
                'message': 'Este flow no tiene una orden asociada. No se puede reenviar el email de confirmación sin una orden.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get optional email override from request body
        to_email = None
        if request.data and isinstance(request.data, dict):
            to_email = request.data.get('to_email')
        
        # Use order email if no override provided
        if not to_email:
            to_email = order.email
        
        if not to_email:
            return Response({
                'success': False,
                'message': 'No email address available for order'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info(f"📧 [SUPERADMIN] Resending email for order {order.order_number} to {to_email} (synchronous)")
        
        # Log manual resend event BEFORE sending
        flow_logger = FlowLogger(flow)
        flow_logger.log_event(
            'EMAIL_MANUAL_RESEND',
            source='superadmin',
            status='info',
            message=f"Manual email resend initiated for order {order.order_number} to {to_email}",
            order=order,
            metadata={
                'resend_to': to_email,
                'resend_by': request.user.email if hasattr(request, 'user') and request.user.is_authenticated else 'superadmin',
            }
        )
        
        # Send email synchronously (like OTP)
        result = send_order_confirmation_email_optimized(
            order_id=str(order.id),
            to_email=to_email,
            flow_id=str(flow.id)
        )
        
        # Log result - send_order_confirmation_email_optimized returns 'completed' on success
        result_status = result.get('status')
        emails_sent = result.get('emails_sent', 0)
        failed_emails = result.get('failed_emails', [])
        
        if result_status == 'completed' and emails_sent > 0:
            logger.info(f"✅ [SUPERADMIN] Email resent successfully for order {order.order_number} - {emails_sent} email(s) sent")
            
            # Log successful manual resend
            flow_logger.log_event(
                'EMAIL_MANUAL_RESEND_SUCCESS',
                source='superadmin',
                status='success',
                message=f"Manual email resend completed successfully to {to_email}",
                order=order,
                metadata={
                    'resend_to': to_email,
                    'emails_sent': emails_sent,
                    'metrics': result.get('metrics', {}),
                }
            )
            
            return Response({
                'success': True,
                'message': f'Email enviado exitosamente a {to_email}',
                'metrics': result.get('metrics', {}),
                'status': result_status,
                'emails_sent': emails_sent
            }, status=status.HTTP_200_OK)
        elif result_status == 'completed' and emails_sent == 0:
            # Completed but no emails sent (shouldn't happen, but handle gracefully)
            error_msg = failed_emails[0].get('error', 'No emails sent') if failed_emails else 'No emails sent'
            logger.warning(f"⚠️ [SUPERADMIN] Email resend completed but no emails sent: {error_msg}")
            
            flow_logger.log_event(
                'EMAIL_MANUAL_RESEND_FAILED',
                source='superadmin',
                status='failure',
                message=f"Manual email resend failed: {error_msg}",
                order=order,
                metadata={
                    'resend_to': to_email,
                    'error': error_msg,
                    'failed_emails': failed_emails,
                    'metrics': result.get('metrics', {}),
                }
            )
            
            return Response({
                'success': False,
                'message': f'Error al enviar el email: {error_msg}',
                'metrics': result.get('metrics', {}),
                'status': result_status,
                'failed_emails': failed_emails
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # Error status
            error_msg = result.get('error', 'Unknown error')
            logger.warning(f"⚠️ [SUPERADMIN] Email resend returned status: {result_status} - {error_msg}")
            
            # Log failed manual resend
            flow_logger.log_event(
                'EMAIL_MANUAL_RESEND_FAILED',
                source='superadmin',
                status='failure',
                message=f"Manual email resend failed: {error_msg}",
                order=order,
                metadata={
                    'resend_to': to_email,
                    'error': error_msg,
                    'metrics': result.get('metrics', {}),
                }
            )
            
            return Response({
                'success': False,
                'message': f'Error al enviar el email: {error_msg}',
                'metrics': result.get('metrics', {}),
                'status': result_status
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except PlatformFlow.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Flow not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error resending email: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al reenviar email: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def bulk_resend_emails(request):
    """
    🚀 ENTERPRISE: Reenvía emails de múltiples flows de forma SÍNCRONA.
    
    Body:
    - flow_ids: Lista de flow IDs para reenviar
    
    Returns:
    - success: bool
    - results: Lista con resultado de cada reenvío
    - summary: Resumen de éxitos/fallos
    """
    try:
        from core.models import PlatformFlow
        from apps.events.email_sender import send_order_confirmation_email_optimized
        from core.flow_logger import FlowLogger
        import concurrent.futures
        from threading import Lock
        
        flow_ids = request.data.get('flow_ids', [])
        if not flow_ids or not isinstance(flow_ids, list):
            return Response({
                'success': False,
                'message': 'flow_ids debe ser una lista de IDs'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(flow_ids) > 50:
            return Response({
                'success': False,
                'message': 'Máximo 50 flows por lote'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info(f"📧 [SUPERADMIN] Bulk resend initiated for {len(flow_ids)} flows")
        
        results = []
        results_lock = Lock()
        
        def process_flow(flow_id: str):
            """Procesa un flow individual"""
            try:
                flow = PlatformFlow.objects.select_related('primary_order').prefetch_related('events__order').get(id=flow_id)
                
                # Buscar orden si no está en primary_order
                order = flow.primary_order
                if not order:
                    order_event = flow.events.filter(order__isnull=False).select_related('order').first()
                    if order_event and order_event.order:
                        order = order_event.order
                        flow.primary_order = order
                        flow.save(update_fields=['primary_order'])
                
                if not order:
                    return {
                        'flow_id': flow_id,
                        'success': False,
                        'message': 'Flow no tiene orden asociada',
                        'order_number': None
                    }
                
                to_email = order.email
                if not to_email:
                    return {
                        'flow_id': flow_id,
                        'success': False,
                        'message': 'Orden no tiene email',
                        'order_number': order.order_number
                    }
                
                # Log manual resend
                flow_logger = FlowLogger(flow)
                flow_logger.log_event(
                    'EMAIL_MANUAL_RESEND',
                    source='superadmin',
                    status='info',
                    message=f"Bulk manual email resend initiated for order {order.order_number}",
                    order=order,
                    metadata={'resend_to': to_email, 'bulk': True}
                )
                
                # Send email
                result = send_order_confirmation_email_optimized(
                    order_id=str(order.id),
                    to_email=to_email,
                    flow_id=str(flow.id)
                )
                
                result_status = result.get('status')
                emails_sent = result.get('emails_sent', 0)
                
                if result_status == 'completed' and emails_sent > 0:
                    flow_logger.log_event(
                        'EMAIL_MANUAL_RESEND_SUCCESS',
                        source='superadmin',
                        status='success',
                        message=f"Bulk manual email resend completed successfully",
                        order=order,
                        metadata={'resend_to': to_email, 'emails_sent': emails_sent, 'bulk': True}
                    )
                    
                    return {
                        'flow_id': flow_id,
                        'success': True,
                        'message': 'Email enviado exitosamente',
                        'order_number': order.order_number,
                        'email': to_email,
                        'metrics': result.get('metrics', {})
                    }
                else:
                    error_msg = result.get('error', 'No emails sent')
                    flow_logger.log_event(
                        'EMAIL_MANUAL_RESEND_FAILED',
                        source='superadmin',
                        status='failure',
                        message=f"Bulk manual email resend failed: {error_msg}",
                        order=order,
                        metadata={'resend_to': to_email, 'error': error_msg, 'bulk': True}
                    )
                    
                    return {
                        'flow_id': flow_id,
                        'success': False,
                        'message': error_msg,
                        'order_number': order.order_number,
                        'email': to_email
                    }
                    
            except PlatformFlow.DoesNotExist:
                return {
                    'flow_id': flow_id,
                    'success': False,
                    'message': 'Flow no encontrado',
                    'order_number': None
                }
            except Exception as e:
                logger.error(f"❌ [SUPERADMIN] Error processing flow {flow_id}: {str(e)}", exc_info=True)
                return {
                    'flow_id': flow_id,
                    'success': False,
                    'message': f'Error: {str(e)}',
                    'order_number': None
                }
        
        # Procesar en paralelo (máximo 5 simultáneos para no sobrecargar)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_flow = {executor.submit(process_flow, flow_id): flow_id for flow_id in flow_ids}
            for future in concurrent.futures.as_completed(future_to_flow):
                result = future.result()
                with results_lock:
                    results.append(result)
        
        # Calcular resumen
        successful = sum(1 for r in results if r.get('success'))
        failed = len(results) - successful
        
        logger.info(f"✅ [SUPERADMIN] Bulk resend completed: {successful} successful, {failed} failed")
        
        return Response({
            'success': True,
            'message': f'Procesados {len(results)} flows: {successful} exitosos, {failed} fallidos',
            'results': results,
            'summary': {
                'total': len(results),
                'successful': successful,
                'failed': failed
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error in bulk resend: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error en reenvío masivo: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def revenue_migration_status(request):
    """
    🚀 ENTERPRISE: Get status of revenue migration (how many orders need migration).
    
    GET /api/v1/superadmin/revenue-migration/status/
    
    Returns:
        - Total paid orders
        - Orders with effective values
        - Orders without effective values
        - Migration percentage
    """
    try:
        from apps.events.models import Order
        from django.db.models import Count, Q
        
        # Count all paid orders
        total_paid_orders = Order.objects.filter(status='paid').count()
        
        # Count orders with effective values
        orders_with_effective = Order.objects.filter(
            status='paid',
            subtotal_effective__isnull=False,
            service_fee_effective__isnull=False
        ).count()
        
        # Count orders without effective values
        orders_without_effective = total_paid_orders - orders_with_effective
        
        # Calculate migration percentage
        migration_percentage = (orders_with_effective / total_paid_orders * 100) if total_paid_orders > 0 else 0
        
        logger.info(f"📊 [SuperAdmin] Revenue migration status: {orders_with_effective}/{total_paid_orders} ({migration_percentage:.2f}%)")
        
        return Response({
            'success': True,
            'status': {
                'total_paid_orders': total_paid_orders,
                'orders_with_effective': orders_with_effective,
                'orders_without_effective': orders_without_effective,
                'migration_percentage': round(migration_percentage, 2),
                'is_complete': orders_without_effective == 0
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting revenue migration status: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al obtener estado de migración: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def migrate_revenue_data(request):
    """
    🚀 ENTERPRISE: Migrate revenue data for orders that don't have effective values.
    
    POST /api/v1/superadmin/revenue-migration/migrate/
    
    Body (optional):
        - batch_size: Number of orders to process per batch (default: 100)
        - dry_run: If true, don't actually migrate (default: false)
    
    Returns:
        - Total orders found
        - Orders migrated
        - Orders failed
        - Success rate
        - Errors (if any)
    """
    try:
        from apps.events.models import Order
        from core.revenue_system import migrate_order_effective_values
        from django.db import transaction
        
        batch_size = int(request.data.get('batch_size', 100))
        dry_run = request.data.get('dry_run', False)
        
        if dry_run:
            logger.info("🔍 [SuperAdmin] Revenue migration DRY RUN mode")
        
        # Get orders that need migration
        orders_to_migrate = Order.objects.filter(
            status='paid',
            subtotal_effective__isnull=True
        ).prefetch_related('items')
        
        total_orders = orders_to_migrate.count()
        
        if total_orders == 0:
            return Response({
                'success': True,
                'message': 'No hay órdenes que requieran migración',
                'summary': {
                    'total_orders': 0,
                    'migrated': 0,
                    'failed': 0,
                    'success_rate': 100.0
                }
            }, status=status.HTTP_200_OK)
        
        if dry_run:
            # Return what would be migrated without actually doing it
            sample_orders = orders_to_migrate[:5]
            sample_data = [{
                'order_number': order.order_number,
                'subtotal': float(order.subtotal),
                'service_fee': float(order.service_fee),
                'discount': float(order.discount),
                'total': float(order.total)
            } for order in sample_orders]
            
            return Response({
                'success': True,
                'dry_run': True,
                'message': f'DRY RUN: Se migrarían {total_orders} órdenes',
                'summary': {
                    'total_orders': total_orders,
                    'migrated': 0,
                    'failed': 0,
                    'success_rate': 0.0
                },
                'sample_orders': sample_data
            }, status=status.HTTP_200_OK)
        
        # Perform migration
        logger.info(f"🚀 [SuperAdmin] Starting revenue migration for {total_orders} orders (batch_size={batch_size})")
        
        migrated_count = 0
        failed_count = 0
        errors = []
        
        # Process in batches
        for i in range(0, total_orders, batch_size):
            batch = orders_to_migrate[i:i+batch_size]
            
            for order in batch:
                try:
                    with transaction.atomic():
                        success = migrate_order_effective_values(order)
                        if success:
                            migrated_count += 1
                            if migrated_count % 50 == 0:
                                logger.info(f"  📊 Progress: {migrated_count}/{total_orders} orders migrated...")
                        else:
                            failed_count += 1
                            errors.append({
                                'order_number': order.order_number,
                                'error': 'Migration returned False'
                            })
                except Exception as e:
                    failed_count += 1
                    error_msg = str(e)
                    errors.append({
                        'order_number': order.order_number,
                        'error': error_msg
                    })
                    logger.error(f"❌ [SuperAdmin] Error migrating order {order.order_number}: {error_msg}", exc_info=True)
        
        success_rate = (migrated_count / total_orders * 100) if total_orders > 0 else 0
        
        logger.info(f"✅ [SuperAdmin] Revenue migration completed: {migrated_count}/{total_orders} ({success_rate:.2f}%)")
        
        return Response({
            'success': True,
            'message': f'Migración completada: {migrated_count} exitosas, {failed_count} fallidas',
            'summary': {
                'total_orders': total_orders,
                'migrated': migrated_count,
                'failed': failed_count,
                'success_rate': round(success_rate, 2)
            },
            'errors': errors[:20] if errors else [],  # Return first 20 errors
            'total_errors': len(errors)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error migrating revenue data: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al migrar datos de revenue: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
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


class CountryViewSet(viewsets.ModelViewSet):
    """
    🚀 ENTERPRISE: Country Management ViewSet for SuperAdmin.
    
    Allows SuperAdmin to manage countries for categorizing experiences and accommodations.
    """
    
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [IsSuperUser]  # ENTERPRISE: Solo superusers
    
    def get_queryset(self):
        """Return active countries by default, or all if requested."""
        queryset = Country.objects.all()
        active_only = self.request.query_params.get('active_only', 'true')
        if active_only.lower() == 'true':
            queryset = queryset.filter(is_active=True)
        return queryset.order_by('display_order', 'name')


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def create_experience_from_json(request):
    """
    🚀 ENTERPRISE: Create experience from JSON data.
    
    POST /api/v1/superadmin/experiences/create-from-json/
    
    Body:
        {
            "experience_data": { ... },  # JSON experience data
            "organizer_id": "uuid"      # Organizer ID to link the experience
        }
    
    Returns:
        {
            "id": "experience-uuid",
            "title": "...",
            "instances_created": 42,
            ...
        }
    """
    try:
        experience_data = request.data.get('experience_data')
        organizer_id = request.data.get('organizer_id')
        
        if not experience_data:
            return Response(
                {"detail": "El campo 'experience_data' es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not organizer_id:
            return Response(
                {"detail": "El campo 'organizer_id' es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate organizer exists and has experience module
        from apps.organizers.models import Organizer
        try:
            organizer = Organizer.objects.get(id=organizer_id)
            if not organizer.has_experience_module:
                return Response(
                    {
                        "detail": f"El organizador '{organizer.name}' no tiene el módulo de experiencias habilitado."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Organizer.DoesNotExist:
            return Response(
                {"detail": f"El organizador con ID '{organizer_id}' no existe."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate and normalize JSON data
        serializer = JsonExperienceCreateSerializer(data=experience_data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create experience
        with transaction.atomic():
            validated_data = serializer.validated_data
            validated_data['organizer'] = organizer
            
            # Extract date_price_overrides from experience_data (no se validan en serializer)
            date_price_overrides = experience_data.get('date_price_overrides', [])
            
            # Create experience using the serializer's create method
            experience = serializer.create(validated_data)
            
            # Generate tour instances from recurrence pattern
            instances_created = 0
            if experience.recurrence_pattern:
                instances_created = generate_tour_instances_from_pattern(experience)
            
            # Create date price overrides (Step 3 - opcional)
            # Step3 permite configurarlos para paid o WhatsApp, pero CreateTourPage solo los crea si isPaid
            # Para el flujo de WhatsApp (end-to-end funcional), también los creamos si están presentes
            overrides_created = 0
            if date_price_overrides and len(date_price_overrides) > 0:
                # Solo crear si es WhatsApp (flujo end-to-end funcional) o paid
                if experience.is_whatsapp_reservation or (not experience.is_free_tour and not experience.is_whatsapp_reservation):
                    from apps.experiences.models import ExperienceDatePriceOverride
                    from datetime import datetime as dt
                    
                    for override_data in date_price_overrides:
                        try:
                            # Parse date
                            override_date = dt.strptime(override_data['date'], '%Y-%m-%d').date()
                            
                            # Parse times if provided
                            start_time = None
                            end_time = None
                            if override_data.get('start_time'):
                                start_time = dt.strptime(override_data['start_time'], '%H:%M').time()
                            if override_data.get('end_time'):
                                end_time = dt.strptime(override_data['end_time'], '%H:%M').time()
                            
                            ExperienceDatePriceOverride.objects.create(
                                experience=experience,
                                date=override_date,
                                start_time=start_time,
                                end_time=end_time,
                                override_adult_price=override_data.get('override_adult_price'),
                                override_child_price=override_data.get('override_child_price'),
                                override_infant_price=override_data.get('override_infant_price'),
                            )
                            overrides_created += 1
                        except (ValueError, KeyError) as e:
                            logger.warning(
                                f"⚠️ [JSON_EXPERIENCE_CREATE] Error creating date price override: {e}"
                            )
                            continue
            
            # Serialize response
            from apps.experiences.serializers import ExperienceSerializer
            response_serializer = ExperienceSerializer(experience)
            
            response_data = response_serializer.data
            response_data['instances_created'] = instances_created
            response_data['overrides_created'] = overrides_created
            
            logger.info(
                f"✅ [JSON_EXPERIENCE_CREATE] Experience '{experience.title}' created from JSON "
                f"(ID: {experience.id}, Organizer: {organizer.name}, "
                f"Instances: {instances_created}, Overrides: {overrides_created})"
            )
            
            return Response(response_data, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(
            f"🔴 [JSON_EXPERIENCE_CREATE] Error creating experience from JSON: {str(e)}",
            exc_info=True
        )
        return Response(
            {
                "detail": f"Error al crear la experiencia: {str(e)}",
                "error_type": type(e).__name__
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

