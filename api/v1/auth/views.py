from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.renderers import JSONRenderer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.otp.models import OTPPurpose
from apps.otp.services import OTPService
from .serializers import (
    UserLoginSerializer, UserCheckSerializer, UserProfileSerializer,
    UserRegistrationSerializer, OTPLoginSerializer, OrganizerOTPSerializer,
    OrganizerOTPValidateSerializer, OrganizerProfileSetupSerializer,
    PasswordChangeSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer
)
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


# Alias para compatibilidad con public_urls
@method_decorator(csrf_exempt, name='dispatch')
class RegistrationView(APIView):
    """Vista de registro (alias para compatibilidad)"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        # TODO: Implementar registro con OTP
        return Response({
            'success': False,
            'message': 'Registro temporal deshabilitado. Usa OTP.'
        }, status=status.HTTP_501_NOT_IMPLEMENTED)


@method_decorator(csrf_exempt, name='dispatch')
class CheckUserView(APIView):
    """
    Verifica si un usuario existe y si tiene contraseña
    """
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    
    def post(self, request):
        serializer = UserCheckSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Email inválido',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        
        try:
            user = User.objects.get(email__iexact=email)
            
            # Verificar si es organizador
            is_organizer = hasattr(user, 'organizer_roles') and user.organizer_roles.exists()
            
            # Si es organizador, verificar si necesita configuración inicial
            # REGLA DE NEGOCIO: Solo verificar onboarding_completed
            needs_setup = False
            if is_organizer:
                try:
                    organizer_user = user.get_primary_organizer_role()
                    if organizer_user and organizer_user.organizer:
                        organizer = organizer_user.organizer
                        needs_setup = not organizer.onboarding_completed
                except Exception as e:
                    logger.warning(f"[CheckUser] Error checking organizer setup for {user.email}: {str(e)}")
                    # Si hay error, asumir que necesita setup
                    needs_setup = True
            
            return Response({
                'exists': True,
                'has_password': user.has_password,
                'is_guest': user.is_guest,
                'is_profile_complete': user.is_profile_complete,
                'is_organizer': is_organizer,
                'needs_setup': needs_setup,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_guest': user.is_guest,
                    'is_organizer': is_organizer
                }
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'exists': False,
                'has_password': False,
                'is_guest': False,
                'is_profile_complete': False,
                'is_organizer': False,
                'needs_setup': False
            }, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    """
    Login tradicional con email y contraseña
    """
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    
    def get(self, request):
        """Debug method - should not be called in production"""
        return Response({
            'success': False,
            'message': 'GET method not allowed for login',
            'debug': 'This endpoint only accepts POST requests'
        }, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        
        # Autenticar usuario
        user = authenticate(request, username=email, password=password)
        
        if user:
            if not user.is_active:
                return Response({
                    'success': False,
                    'message': 'Cuenta desactivada'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Generar tokens JWT
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            
            # Actualizar último login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
        
            return Response({
                    'success': True,
                    'message': 'Login exitoso',
                    'token': access_token,
                    'refresh': str(refresh),
                    'user': UserProfileSerializer(user).data
                }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Credenciales incorrectas'
            }, status=status.HTTP_401_UNAUTHORIZED)


@method_decorator(csrf_exempt, name='dispatch')
class OTPLoginView(APIView):
    """
    Login/registro con OTP
    """
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    
    def post(self, request):
        serializer = OTPLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        code = serializer.validated_data['code']
        
        # Validar OTP
        result = OTPService.validate_code(
            email=email,
            code=code,
            purpose=OTPPurpose.LOGIN,
            request=request
        )
        
        if not result['success']:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Buscar o crear usuario
                user, created = User.objects.get_or_create(
                    email__iexact=email,
                    defaults={
                        'username': email.split('@')[0],
                        'email': email,
                        'is_guest': True,
                        'is_active': True
                    }
                )
                
                # Si es un usuario existente, actualizar último login
                if not created:
                    user.last_login = timezone.now()
                    user.save(update_fields=['last_login'])
                
                # Generar tokens JWT
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)
                
                return Response({
                    'success': True,
                    'message': 'Acceso autorizado',
                    'access_token': access_token,
                    'refresh': str(refresh),
                    'user': UserProfileSerializer(user).data,
                    'is_new_user': created,
                    'requires_profile_completion': not user.is_profile_complete
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error in OTP login: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error interno del sistema'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserProfileView(APIView):
    """
    Vista para obtener y actualizar el perfil del usuario
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Obtener perfil actual"""
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request):
        """Actualizar perfil"""
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                user = serializer.save()
                
                # Si se completó el perfil por primera vez
                if (user.first_name and user.last_name and 
                    user.is_guest and not user.profile_completed_at):
                    user.mark_profile_complete()
                
                return Response({
                    'success': True,
                    'message': 'Perfil actualizado',
                    'user': UserProfileSerializer(user).data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error updating profile: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error al actualizar perfil'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LogoutView(APIView):
    """
    Cerrar sesión
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # Invalidar refresh token si se proporciona
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
                
            return Response({
                'success': True,
                'message': 'Sesión cerrada correctamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error logging out: {str(e)}")
            return Response({
                'success': True,  # Siempre exitoso desde el punto de vista del cliente
                'message': 'Sesión cerrada'
            }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_guest_user_from_purchase(request):
    """
    Crea un usuario invitado automáticamente desde una compra
    """
    email = request.data.get('email')
    first_name = request.data.get('first_name', '')
    last_name = request.data.get('last_name', '')
    order_id = request.data.get('order_id')
    
    if not email:
        return Response({
            'success': False,
            'message': 'Email requerido'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            # Verificar si ya existe
            user, created = User.objects.get_or_create(
                email__iexact=email,
                defaults={
                    'username': email.split('@')[0],
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'is_guest': True,
                    'is_active': True
                }
            )
            
            # Si no es nuevo pero es guest, actualizar datos si están vacíos
            if not created and user.is_guest:
                updated = False
                if not user.first_name and first_name:
                    user.first_name = first_name
                    updated = True
                if not user.last_name and last_name:
                    user.last_name = last_name
                    updated = True
                if updated:
                    user.save(update_fields=['first_name', 'last_name'])
            
            return Response({
                'success': True,
                'user_created': created,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_guest': user.is_guest
                },
                'message': 'Usuario guest creado' if created else 'Usuario existente actualizado'
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
            
    except Exception as e:
        logger.error(f"Error creating guest user: {str(e)}")
        return Response({
            'success': False,
            'message': 'Error al crear usuario'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ========================================
# PASSWORD MANAGEMENT SYSTEM
# ========================================

@method_decorator(csrf_exempt, name='dispatch')
class PasswordChangeView(APIView):
    """
    Cambiar contraseña con contraseña actual
    Requiere autenticación y conocer la contraseña actual
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]
    
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        current_password = serializer.validated_data['current_password']
        new_password = serializer.validated_data['new_password']
        
        user = request.user
        
        # Verificar contraseña actual
        if not user.check_password(current_password):
            return Response({
                'success': False,
                'message': 'La contraseña actual es incorrecta'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar que la nueva contraseña sea diferente
        if current_password == new_password:
            return Response({
                'success': False,
                'message': 'La nueva contraseña debe ser diferente a la actual'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Cambiar contraseña
            user.set_password(new_password)
            user.last_password_change = timezone.now()
            user.save(update_fields=['password', 'last_password_change'])
            
            logger.info(f"Password changed successfully for user {user.email}")
            
            return Response({
                'success': True,
                'message': 'Contraseña cambiada exitosamente',
                'last_password_change': user.last_password_change
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error changing password for user {user.email}: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error al cambiar la contraseña'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetView(APIView):
    """
    Solicitar restablecimiento de contraseña vía OTP
    Envía un código de 6 dígitos al email del usuario
    """
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Email inválido',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        
        # Verificar que el usuario existe
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Por seguridad, no revelar que el usuario no existe
            # Devolver éxito pero no enviar email
            return Response({
                'success': True,
                'message': 'Si el email existe, recibirás un código de restablecimiento',
                'email': email
            }, status=status.HTTP_200_OK)
        
        # Generar y enviar OTP
        result = OTPService.generate_and_send(
            email=email,
            purpose=OTPPurpose.PASSWORD_RESET,
            user=user,
            metadata={'action': 'password_reset'},
            request=request
        )
        
        if result['success']:
            otp = result['otp']
            logger.info(f"Password reset OTP sent to {email}")
            
            return Response({
                'success': True,
                'message': 'Código de restablecimiento enviado a tu email',
                'email': email,
                'expires_at': otp.expires_at,
                'time_remaining_minutes': int(otp.time_remaining.total_seconds() // 60)
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetConfirmView(APIView):
    """
    Restablecer contraseña con código OTP
    Permite cambiar la contraseña sin conocer la contraseña actual
    """
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        code = serializer.validated_data['code']
        new_password = serializer.validated_data['new_password']
        
        # Validar código OTP
        result = OTPService.validate_code(
            email=email,
            code=code,
            purpose=OTPPurpose.PASSWORD_RESET,
            request=request
        )
        
        if not result['success']:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Obtener usuario
                user = User.objects.get(email__iexact=email)
                
                # Cambiar contraseña
                user.set_password(new_password)
                user.last_password_change = timezone.now()
                user.save(update_fields=['password', 'last_password_change'])
                
                logger.info(f"Password reset successfully for user {user.email}")
                
                # Generar tokens JWT para login automático
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)
                
                return Response({
                    'success': True,
                    'message': 'Contraseña restablecida exitosamente',
                    'access': access_token,
                    'refresh': str(refresh),
                    'user': UserProfileSerializer(user).data
                }, status=status.HTTP_200_OK)
                
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Usuario no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error resetting password for {email}: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error al restablecer la contraseña'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_password_view(request):
    """Vista para establecer contraseña (legacy)"""
    return Response({
        'success': False,
        'message': 'Usa /auth/change-password/ o /auth/password-reset/ según tu caso'
    }, status=status.HTTP_410_GONE)


@method_decorator(csrf_exempt, name='dispatch')
class EmailTokenObtainPairView(APIView):
    """Vista para obtener token JWT con email (para organizadores)"""
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        
        # Autenticar usuario
        user = authenticate(request, username=email, password=password)
        
        if user:
            if not user.is_active:
                return Response({
                    'success': False,
                    'message': 'Cuenta desactivada'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Generar tokens JWT
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            
            # Actualizar último login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
        
            return Response({
                'access': access_token,
                'refresh': str(refresh),
                'user': UserProfileSerializer(user).data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Credenciales incorrectas'
            }, status=status.HTTP_401_UNAUTHORIZED)


# ========================================
# ORGANIZER OTP AUTHENTICATION SYSTEM
# ========================================

@method_decorator(csrf_exempt, name='dispatch')
class OrganizerOTPSendView(APIView):
    """
    Enviar código OTP para organizadores
    """
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    
    def post(self, request):
        serializer = OrganizerOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Email inválido',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        
        # Verificar que el usuario existe y es organizador
        try:
            user = User.objects.get(email__iexact=email)
            is_organizer = hasattr(user, 'organizer_roles') and user.organizer_roles.exists()
            
            if not is_organizer:
                return Response({
                    'success': False,
                    'message': 'Este email no está asociado a una cuenta de organizador'
                }, status=status.HTTP_404_NOT_FOUND)
                
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'No se encontró una cuenta con este email'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Generar y enviar OTP
        result = OTPService.generate_and_send(
            email=email,
            purpose=OTPPurpose.LOGIN,
            user=user,
            metadata={'login_method': 'organizer_otp'},
            request=request
        )
        
        if result['success']:
            otp = result['otp']
            return Response({
                'success': True,
                'message': 'Código de acceso enviado a tu email',
                'expires_at': otp.expires_at,
                'time_remaining_minutes': int(otp.time_remaining.total_seconds() // 60)
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class OrganizerOTPValidateView(APIView):
    """
    Validar código OTP y autenticar organizador
    """
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]
    
    def post(self, request):
        serializer = OrganizerOTPValidateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        code = serializer.validated_data['code']
        
        # Validar OTP
        result = OTPService.validate_code(
            email=email,
            code=code,
            purpose=OTPPurpose.LOGIN,
            request=request
        )
        
        if not result['success']:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email__iexact=email)
            
            # Verificar que es organizador
            is_organizer = hasattr(user, 'organizer_roles') and user.organizer_roles.exists()
            if not is_organizer:
                return Response({
                    'success': False,
                    'message': 'Usuario no es organizador'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Actualizar último login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            # Generar tokens JWT
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            
            # Obtener datos del organizador principal
            organizer_user = user.get_primary_organizer_role()
            organizer = organizer_user.organizer if organizer_user else None
            
            # REGLA DE NEGOCIO: Solo verificar onboarding_completed
            if organizer:
                needs_setup = not organizer.onboarding_completed
            elif is_organizer:
                # Si es organizador pero no tiene organizador principal, necesita setup
                needs_setup = True
            else:
                needs_setup = False
            
            return Response({
                'success': True,
                'message': 'Acceso autorizado',
                'access': access_token,
                'refresh': str(refresh),
                'user': UserProfileSerializer(user).data,
                'needs_setup': needs_setup,
                'organizer': {
                    'id': str(organizer.id) if organizer else None,
                    'name': organizer.name if organizer else None,
                    'slug': organizer.slug if organizer else None,
                    'is_temporary': organizer.is_temporary if organizer else True,
                    'email_validated': organizer.email_validated if organizer else False
                } if organizer else None
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Usuario no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in organizer OTP validation: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error interno del sistema'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class OrganizerProfileSetupView(APIView):
    """
    Configuración inicial del perfil de organizador
    GET: Verificar si el perfil está completo
    POST: Completar el perfil
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]
    
    def get(self, request):
        """
        Verificar si el perfil del organizador está completo.
        
        REGLA DE NEGOCIO SIMPLE:
        - Si onboarding_completed = False → needs_setup = True (modal aparece)
        - Si onboarding_completed = True → needs_setup = False (modal NO aparece)
        """
        try:
            user = request.user
            logger.info(f"[ProfileSetup] Checking profile status for user: {user.email} (ID: {user.id})")
            
            # Verificar que el usuario es organizador
            if not (hasattr(user, 'organizer_roles') and user.organizer_roles.exists()):
                logger.info(f"[ProfileSetup] User {user.email} is not an organizer")
                return Response({
                    'is_organizer': False,
                    'needs_setup': False,
                    'message': 'Usuario no es organizador'
                }, status=status.HTTP_200_OK)
            
            # Obtener el organizador principal del usuario
            organizer_user = user.get_primary_organizer_role()
            if not organizer_user:
                logger.error(f"[ProfileSetup] User {user.email} has organizer_roles but get_primary_organizer_role() returned None")
                return Response({
                    'is_organizer': False,
                    'needs_setup': False,
                    'message': 'Error al obtener organizador principal'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            organizer = organizer_user.organizer
            
            # REGLA DE NEGOCIO: Solo verificar onboarding_completed
            needs_setup = not organizer.onboarding_completed
            
            logger.info(
                f"[ProfileSetup] Organizer: {organizer.name} (ID: {organizer.id}) | "
                f"onboarding_completed: {organizer.onboarding_completed} | needs_setup: {needs_setup}"
            )
            
            return Response({
                'is_organizer': True,
                'needs_setup': needs_setup,
                'organizer': {
                    'id': str(organizer.id),
                    'name': organizer.name,
                    'slug': organizer.slug,
                    'contact_email': organizer.contact_email,
                    'representative_name': organizer.representative_name,
                    'contact_phone': organizer.contact_phone,
                    'is_temporary': organizer.is_temporary,
                    'email_validated': organizer.email_validated,
                    'onboarding_completed': organizer.onboarding_completed
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(
                f"[ProfileSetup] Error checking organizer profile status for user {request.user.email}: {str(e)}",
                exc_info=True
            )
            return Response({
                'is_organizer': False,
                'needs_setup': False,
                'message': 'Error al verificar perfil'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request):
        """
        Completar configuración inicial del perfil de organizador.
        
        REGLA DE NEGOCIO:
        - Al completar este endpoint, SIEMPRE se marca onboarding_completed = True
        - Esto asegura que el modal NO aparezca nuevamente
        """
        # Validación: Verificar que el usuario es organizador
        if not (hasattr(request.user, 'organizer_roles') and request.user.organizer_roles.exists()):
            return Response({
                'success': False,
                'message': 'Usuario no es organizador'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Validación: Verificar datos del serializer
        serializer = OrganizerProfileSetupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                user = request.user
                logger.info(f"[ProfileSetup] Starting profile setup for user: {user.email} (ID: {user.id})")
                
                # Obtener el organizador principal
                organizer_user = user.get_primary_organizer_role()
                if not organizer_user:
                    logger.error(f"[ProfileSetup] User {user.email} has organizer_roles but get_primary_organizer_role() returned None")
                    return Response({
                        'success': False,
                        'message': 'Error al obtener organizador principal'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
                organizer = organizer_user.organizer
                logger.info(f"[ProfileSetup] Updating organizer: {organizer.name} (ID: {organizer.id})")
                
                # ============================================================
                # ACTUALIZACIÓN DE DATOS DEL ORGANIZADOR
                # ============================================================
                
                # Actualizar nombre de organización
                organization_name = serializer.validated_data.get('organization_name')
                if organization_name:
                    organizer.name = organization_name.strip()
                    # Generar slug único basado en el nombre
                    from django.utils.text import slugify
                    base_slug = slugify(organizer.name)
                    counter = 1
                    final_slug = base_slug
                    while organizer.__class__.objects.filter(slug=final_slug).exclude(id=organizer.id).exists():
                        final_slug = f"{base_slug}-{counter}"
                        counter += 1
                    organizer.slug = final_slug
                    logger.info(f"[ProfileSetup] Updated organization name: '{organizer.name}' (slug: {organizer.slug})")
                
                # Actualizar nombre del representante
                contact_name = serializer.validated_data.get('contact_name')
                if contact_name:
                    organizer.representative_name = contact_name.strip()
                    # También actualizar el usuario
                    if ' ' in contact_name:
                        first_name, last_name = contact_name.strip().split(' ', 1)
                        user.first_name = first_name
                        user.last_name = last_name
                    else:
                        user.first_name = contact_name.strip()
                    logger.info(f"[ProfileSetup] Updated representative name: '{contact_name}'")
                
                # Actualizar teléfono de contacto
                contact_phone = serializer.validated_data.get('contact_phone')
                if contact_phone:
                    organizer.contact_phone = contact_phone.strip()
                    organizer.representative_phone = contact_phone.strip()
                    user.phone_number = contact_phone.strip()
                    logger.info(f"[ProfileSetup] Updated contact phone: '{contact_phone}'")
                
                # ============================================================
                # MARCAR ONBOARDING COMO COMPLETADO
                # ============================================================
                # CRÍTICO: Siempre marcar onboarding_completed = True
                # Esto asegura que el modal NO aparezca nuevamente
                organizer.is_temporary = False
                organizer.email_validated = True
                organizer.onboarding_completed = True
                
                organizer.save()
                logger.info(
                    f"[ProfileSetup] Onboarding marked as completed - "
                    f"onboarding_completed: {organizer.onboarding_completed}"
                )
                
                # ============================================================
                # ACTUALIZACIÓN DE DATOS DEL USUARIO
                # ============================================================
                
                # Actualizar contraseña si se proporciona
                password = serializer.validated_data.get('password')
                if password:
                    user.set_password(password)
                    user.last_password_change = timezone.now()
                    logger.info(f"[ProfileSetup] Password updated for user")
                
                # Marcar perfil de usuario como completo
                if user.is_guest or not user.profile_completed_at:
                    user.mark_profile_complete()
                    logger.info(f"[ProfileSetup] User profile marked as complete")
                else:
                    user.save()
                
                logger.info(
                    f"[ProfileSetup] ✅ Profile setup completed successfully for {user.email} - "
                    f"Organization: {organizer.name} (ID: {organizer.id})"
                )
                
                return Response({
                    'success': True,
                    'message': 'Perfil configurado exitosamente',
                    'organizer': {
                        'id': str(organizer.id),
                        'name': organizer.name,
                        'slug': organizer.slug,
                        'is_temporary': organizer.is_temporary,
                        'email_validated': organizer.email_validated,
                        'onboarding_completed': organizer.onboarding_completed
                    },
                    'user': UserProfileSerializer(user).data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(
                f"[ProfileSetup] ❌ Error in organizer profile setup for user {request.user.email}: {str(e)}",
                exc_info=True
            )
            return Response({
                'success': False,
                'message': 'Error al configurar perfil'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)