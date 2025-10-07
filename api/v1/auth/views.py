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
    OrganizerOTPValidateSerializer, OrganizerProfileSetupSerializer
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
            needs_setup = False
            if is_organizer:
                try:
                    organizer_user = user.organizer_roles.first()
                    if organizer_user and organizer_user.organizer:
                        organizer = organizer_user.organizer
                        # Necesita setup si no tiene nombre de organización o es temporal
                        needs_setup = (not organizer.name or 
                                     organizer.name.startswith('Organizador ') or 
                                     organizer.is_temporary or 
                                     not organizer.email_validated)
                except:
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


# Vistas adicionales para compatibilidad
class PasswordResetView(APIView):
    """Vista de reset de contraseña (placeholder)"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        return Response({
            'success': False,
            'message': 'Usa OTP para recuperar acceso'
        }, status=status.HTTP_501_NOT_IMPLEMENTED)


class PasswordResetConfirmView(APIView):
    """Vista de confirmación de reset (placeholder)"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        return Response({
            'success': False,
            'message': 'Usa OTP para recuperar acceso'
        }, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_password_view(request):
    """Vista para establecer contraseña"""
    return Response({
        'success': False,
        'message': 'Usa el perfil para cambiar contraseña'
    }, status=status.HTTP_501_NOT_IMPLEMENTED)


class PasswordChangeView(APIView):
    """Vista para cambiar contraseña"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        return Response({
            'success': False,
            'message': 'Usa el perfil para cambiar contraseña'
        }, status=status.HTTP_501_NOT_IMPLEMENTED)


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
            
            # Obtener datos del organizador
            organizer_user = user.organizer_roles.first()
            organizer = organizer_user.organizer if organizer_user else None
            
            # Verificar si necesita configuración inicial
            needs_setup = False
            if organizer:
                needs_setup = (not organizer.name or 
                             organizer.name.startswith('Organizador ') or 
                             organizer.is_temporary or 
                             not organizer.email_validated)
            else:
                needs_setup = True
            
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
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]
    
    def post(self, request):
        # Verificar que el usuario es organizador
        if not (hasattr(request.user, 'organizer_roles') and request.user.organizer_roles.exists()):
            return Response({
                'success': False,
                'message': 'Usuario no es organizador'
            }, status=status.HTTP_403_FORBIDDEN)
        
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
                organizer_user = user.organizer_roles.first()
                organizer = organizer_user.organizer
                
                # Actualizar datos del organizador
                organization_name = serializer.validated_data.get('organization_name')
                contact_name = serializer.validated_data.get('contact_name')
                contact_phone = serializer.validated_data.get('contact_phone')
                password = serializer.validated_data.get('password')
                
                if organization_name:
                    organizer.name = organization_name
                    # Generar slug único
                    from django.utils.text import slugify
                    base_slug = slugify(organization_name)
                    counter = 1
                    final_slug = base_slug
                    while organizer.__class__.objects.filter(slug=final_slug).exclude(id=organizer.id).exists():
                        final_slug = f"{base_slug}-{counter}"
                        counter += 1
                    organizer.slug = final_slug
                
                if contact_name:
                    organizer.representative_name = contact_name
                    # También actualizar el usuario
                    if ' ' in contact_name:
                        first_name, last_name = contact_name.split(' ', 1)
                        user.first_name = first_name
                        user.last_name = last_name
                    else:
                        user.first_name = contact_name
                
                if contact_phone:
                    organizer.contact_phone = contact_phone
                    organizer.representative_phone = contact_phone
                    user.phone_number = contact_phone
                
                # Marcar como configurado
                organizer.is_temporary = False
                organizer.email_validated = True
                organizer.onboarding_completed = True
                
                organizer.save()
                
                # Actualizar contraseña del usuario si se proporciona
                if password:
                    user.set_password(password)
                    user.last_password_change = timezone.now()
                
                # Marcar perfil de usuario como completo si no lo está
                if user.is_guest or not user.profile_completed_at:
                    user.mark_profile_complete()
                else:
                    user.save()
                
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
            logger.error(f"Error in organizer profile setup: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error al configurar perfil'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)