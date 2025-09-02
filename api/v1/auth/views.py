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
    UserRegistrationSerializer, OTPLoginSerializer
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
            
            return Response({
                'exists': True,
                'has_password': user.has_password,
                'is_guest': user.is_guest,
                'is_profile_complete': user.is_profile_complete,
                'is_organizer': is_organizer,
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
                'is_organizer': False
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