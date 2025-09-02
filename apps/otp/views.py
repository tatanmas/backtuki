from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from .models import OTPPurpose
from .services import OTPService
from .serializers import (
    OTPGenerateSerializer, OTPValidateSerializer, OTPResendSerializer,
    OTPStatusSerializer, OTPResponseSerializer, OTPValidationResponseSerializer,
    EventCreationOTPSerializer, LoginOTPSerializer, TicketAccessOTPSerializer
)
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class OTPRateThrottle(AnonRateThrottle):
    """Rate limiting específico para OTP"""
    scope = 'otp'
    rate = '10/hour'  # Máximo 10 códigos por hora por IP


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(never_cache, name='dispatch')
class OTPGenerateView(APIView):
    """
    Vista para generar códigos OTP
    """
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]
    
    def post(self, request):
        serializer = OTPGenerateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        purpose = serializer.validated_data['purpose']
        metadata = serializer.validated_data.get('metadata', {})
        
        # Buscar usuario existente
        user = None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            pass
        
        # Generar y enviar código
        result = OTPService.generate_and_send(
            email=email,
            purpose=purpose,
            user=user,
            metadata=metadata,
            request=request
        )
        
        if result['success']:
            otp = result['otp']
            response_data = {
                'success': True,
                'message': result['message'],
                'expires_at': otp.expires_at,
                'time_remaining_minutes': int(otp.time_remaining.total_seconds() // 60)
            }
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(never_cache, name='dispatch')
class OTPValidateView(APIView):
    """
    Vista para validar códigos OTP
    """
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]
    
    def post(self, request):
        serializer = OTPValidateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        code = serializer.validated_data['code']
        purpose = serializer.validated_data['purpose']
        
        # Validar código
        result = OTPService.validate_code(
            email=email,
            code=code,
            purpose=purpose,
            request=request
        )
        
        if result['success']:
            otp = result['otp']
            user = result['user']
            
            response_data = {
                'success': True,
                'message': result['message'],
                'user_id': user.id if user else None,
                'user_email': user.email if user else email,
                'is_new_user': user is None,
            }
            
            # Lógica específica según el propósito
            if purpose == OTPPurpose.EVENT_CREATION:
                response_data.update({
                    'next_step': 'create_event',
                    'requires_onboarding': user is None or not hasattr(user, 'organizer_profile')
                })
            
            elif purpose == OTPPurpose.LOGIN:
                # Para login, generar tokens JWT automáticamente
                from rest_framework_simplejwt.tokens import RefreshToken
                from core.utils import generate_username
                
                # Si no existe usuario, crearlo
                if user is None:
                    user = User.objects.create_user(
                        email=email,
                        username=generate_username(email),
                        first_name='',
                        last_name='',
                        is_guest=True
                    )
                    is_new_user = True
                else:
                    is_new_user = False
                
                # Generar tokens JWT
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)
                
                # Actualizar último login
                from django.utils import timezone
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
                
                response_data.update({
                    'access_token': access_token,
                    'refresh_token': str(refresh),
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'is_guest': user.is_guest,
                        'is_profile_complete': user.is_profile_complete
                    },
                    'is_new_user': is_new_user,
                    'next_step': 'dashboard' if not is_new_user else 'complete_profile',
                    'requires_onboarding': False
                })
            
            elif purpose == OTPPurpose.TICKET_ACCESS:
                response_data.update({
                    'next_step': 'view_tickets',
                    'requires_onboarding': False
                })
            
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class OTPResendView(APIView):
    """
    Vista para reenviar códigos OTP
    """
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]
    
    def post(self, request):
        serializer = OTPResendSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        purpose = serializer.validated_data['purpose']
        
        # Reenviar código
        result = OTPService.resend_code(
            email=email,
            purpose=purpose,
            request=request
        )
        
        if result['success']:
            otp = result['otp']
            return Response({
                'success': True,
                'message': 'Código reenviado correctamente',
                'expires_at': otp.expires_at,
                'time_remaining_minutes': int(otp.time_remaining.total_seconds() // 60)
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class OTPStatusView(APIView):
    """
    Vista para consultar el estado de un OTP
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = OTPStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        purpose = serializer.validated_data['purpose']
        
        # Obtener información del código
        info = OTPService.get_active_code_info(email, purpose)
        
        if info['exists']:
            return Response({
                'success': True,
                'has_active_code': True,
                'expires_at': info['expires_at'],
                'time_remaining_minutes': int(info['time_remaining'].total_seconds() // 60),
                'attempts': info['attempts'],
                'max_attempts': info['max_attempts']
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': True,
                'has_active_code': False,
                'message': 'No hay código activo'
            }, status=status.HTTP_200_OK)


# Vistas específicas por propósito

@method_decorator(csrf_exempt, name='dispatch')
class EventCreationOTPView(APIView):
    """
    Vista específica para OTP de creación de eventos
    """
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]
    
    def post(self, request):
        serializer = EventCreationOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        event_title = serializer.validated_data.get('event_title', '')
        is_paid_event = serializer.validated_data.get('is_paid_event', False)
        
        # Metadatos específicos para eventos
        metadata = {
            'event_title': event_title,
            'is_paid_event': is_paid_event,
            'creation_flow': 'public_quick'
        }
        
        # Buscar usuario existente
        user = None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            pass
        
        result = OTPService.generate_and_send(
            email=email,
            purpose=OTPPurpose.EVENT_CREATION,
            user=user,
            metadata=metadata,
            request=request
        )
        
        if result['success']:
            otp = result['otp']
            return Response({
                'success': True,
                'message': 'Código enviado para crear tu evento',
                'expires_at': otp.expires_at,
                'time_remaining_minutes': int(otp.time_remaining.total_seconds() // 60),
                'is_new_organizer': user is None
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class LoginOTPView(APIView):
    """
    Vista específica para OTP de login
    """
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]
    
    def post(self, request):
        serializer = LoginOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        remember_me = serializer.validated_data.get('remember_me', False)
        
        # Verificar si el usuario existe
        try:
            user = User.objects.get(email__iexact=email)
            user_exists = True
        except User.DoesNotExist:
            user = None
            user_exists = False
        
        metadata = {
            'remember_me': remember_me,
            'user_exists': user_exists,
            'login_method': 'otp'
        }
        
        result = OTPService.generate_and_send(
            email=email,
            purpose=OTPPurpose.LOGIN,
            user=user,
            metadata=metadata,
            request=request
        )
        
        if result['success']:
            otp = result['otp']
            return Response({
                'success': True,
                'message': 'Código de acceso enviado',
                'expires_at': otp.expires_at,
                'time_remaining_minutes': int(otp.time_remaining.total_seconds() // 60),
                'user_exists': user_exists
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class TicketAccessOTPView(APIView):
    """
    Vista específica para OTP de acceso a tickets
    """
    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]
    
    def post(self, request):
        serializer = TicketAccessOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Datos inválidos',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        order_id = serializer.validated_data.get('order_id')
        event_id = serializer.validated_data.get('event_id')
        
        # Verificar que el usuario tenga tickets
        # TODO: Implementar verificación de tickets/órdenes
        
        metadata = {
            'order_id': order_id,
            'event_id': event_id,
            'access_type': 'guest_ticket_access'
        }
        
        # Buscar usuario
        user = None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            pass
        
        result = OTPService.generate_and_send(
            email=email,
            purpose=OTPPurpose.TICKET_ACCESS,
            user=user,
            metadata=metadata,
            request=request
        )
        
        if result['success']:
            otp = result['otp']
            return Response({
                'success': True,
                'message': 'Código enviado para acceder a tus tickets',
                'expires_at': otp.expires_at,
                'time_remaining_minutes': int(otp.time_remaining.total_seconds() // 60)
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)


# Vista para limpieza de códigos (admin)
@api_view(['POST'])
@permission_classes([AllowAny])  # TODO: Cambiar a IsAdminUser
def cleanup_expired_codes(request):
    """
    Endpoint para limpiar códigos expirados (uso administrativo)
    """
    try:
        count = OTPService.cleanup_expired_codes()
        return Response({
            'success': True,
            'message': f'{count} códigos expirados eliminados',
            'deleted_count': count
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error en limpieza de códigos: {str(e)}")
        return Response({
            'success': False,
            'message': 'Error en la limpieza'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
