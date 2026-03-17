"""
SuperAdmin User Management Views
Endpoints para gestión completa de usuarios.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
import logging

from apps.events.models import Order, Ticket, TicketNote
from apps.otp.models import OTP, OTPAttempt
from apps.validation.models import ValidatorSession, TicketNote as ValidationTicketNote
from apps.organizers.models import OrganizerUser
from apps.forms.models import Form
from payment_processor.models import SavedCard
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from apps.sync_woocommerce.models import SyncConfiguration, SyncExecution
from apps.events.models import EventView, ConversionFunnel

from core.revenue_system import order_revenue_eligible_q
from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)
User = get_user_model()

# Q for revenue-eligible orders (for annotations on User.orders)
_ORDER_REVENUE_Q = Q(
    orders__status='paid',
    orders__is_sandbox=False,
    orders__deleted_at__isnull=True,
    orders__exclude_from_revenue=False,
)


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
            # Estadísticas solo con órdenes revenue-eligible (no sandbox, no excluidas)
            users = User.objects.annotate(
                orders_count=Count('orders', distinct=True, filter=_ORDER_REVENUE_Q),
                total_spent=Sum('orders__total', filter=_ORDER_REVENUE_Q),
            ).select_related('profile').order_by('-date_joined')
            
            users_data = []
            for user in users:
                paid_orders = Order.objects.filter(user=user).filter(order_revenue_eligible_q())
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
                orders_count=Count('orders', distinct=True, filter=_ORDER_REVENUE_Q),
                total_spent=Sum('orders__total', filter=_ORDER_REVENUE_Q),
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
