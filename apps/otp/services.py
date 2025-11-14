from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import OTP, OTPPurpose, OTPAttempt
from email.mime.image import MIMEImage
import logging
import os

logger = logging.getLogger(__name__)
User = get_user_model()


class OTPService:
    """
    Servicio principal para manejo de códigos OTP
    """
    
    # Configuración de expiración por propósito (en minutos)
    EXPIRY_TIMES = {
        OTPPurpose.EVENT_CREATION: 15,
        OTPPurpose.LOGIN: 10,
        OTPPurpose.TICKET_ACCESS: 10,
        OTPPurpose.PASSWORD_RESET: 30,
        OTPPurpose.EMAIL_VERIFICATION: 60,
        OTPPurpose.ACCOUNT_CREATION: 15,
    }
    
    # Límites de intentos por propósito
    MAX_ATTEMPTS = {
        OTPPurpose.EVENT_CREATION: 5,
        OTPPurpose.LOGIN: 3,
        OTPPurpose.TICKET_ACCESS: 5,
        OTPPurpose.PASSWORD_RESET: 5,
        OTPPurpose.EMAIL_VERIFICATION: 5,
        OTPPurpose.ACCOUNT_CREATION: 5,
    }
    
    @classmethod
    def generate_and_send(cls, email, purpose, user=None, metadata=None, 
                         request=None, custom_expiry=None):
        """
        Genera y envía un código OTP por email
        
        Args:
            email: Email destinatario
            purpose: Propósito del código (OTPPurpose)
            user: Usuario asociado (opcional)
            metadata: Metadatos adicionales
            request: Request HTTP para obtener IP y User-Agent
            custom_expiry: Tiempo de expiración personalizado en minutos
            
        Returns:
            dict: {'success': bool, 'otp': OTP, 'message': str}
        """
        try:
            with transaction.atomic():
                # Determinar tiempo de expiración
                expiry_minutes = custom_expiry or cls.EXPIRY_TIMES.get(purpose, 10)
                
                # Obtener información de la request
                ip_address = None
                user_agent = None
                if request:
                    ip_address = cls._get_client_ip(request)
                    user_agent = request.META.get('HTTP_USER_AGENT', '')
                
                # Generar código
                otp = OTP.objects.generate_code(
                    email=email,
                    purpose=purpose,
                    expiry_minutes=expiry_minutes,
                    user=user,
                    metadata=metadata or {}
                )
                
                # Actualizar campos de tracking
                otp.ip_address = ip_address
                otp.user_agent = user_agent
                otp.save(update_fields=['ip_address', 'user_agent'])
                
                # Enviar email
                email_sent = cls._send_otp_email(otp)
                
                if email_sent:
                    logger.info(f"OTP generado y enviado: {email} - {purpose}")
                    return {
                        'success': True,
                        'otp': otp,
                        'message': 'Código enviado correctamente'
                    }
                else:
                    # Si falla el envío, invalidar el código
                    otp.invalidate()
                    return {
                        'success': False,
                        'otp': None,
                        'message': 'Error al enviar el código'
                    }
                    
        except Exception as e:
            logger.error(f"Error generando OTP: {str(e)}")
            return {
                'success': False,
                'otp': None,
                'message': 'Error interno del sistema'
            }
    
    @classmethod
    def validate_code(cls, email, code, purpose, request=None):
        """
        Valida un código OTP
        
        Args:
            email: Email del usuario
            code: Código a validar
            purpose: Propósito del código
            request: Request HTTP para logging
            
        Returns:
            dict: {'success': bool, 'otp': OTP, 'message': str, 'user': User}
        """
        try:
            # Obtener información de la request
            ip_address = None
            user_agent = None
            if request:
                ip_address = cls._get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Buscar OTP activo
            otp = OTP.objects.get_active_for_email(email, purpose)
            
            if not otp:
                cls._log_attempt(None, code, False, ip_address, user_agent)
                return {
                    'success': False,
                    'otp': None,
                    'message': 'No hay código activo para este email',
                    'user': None
                }
            
            # Verificar límite de intentos
            max_attempts = cls.MAX_ATTEMPTS.get(purpose, 3)
            if otp.attempts >= max_attempts:
                otp.invalidate()
                cls._log_attempt(otp, code, False, ip_address, user_agent)
                return {
                    'success': False,
                    'otp': otp,
                    'message': 'Demasiados intentos. Solicita un nuevo código.',
                    'user': otp.user
                }
            
            # Incrementar intentos
            otp.increment_attempts()
            
            # Validar código
            is_valid, validated_otp, error_message = OTP.objects.validate_code(
                email, code, purpose
            )
            
            # Log del intento
            cls._log_attempt(otp, code, is_valid, ip_address, user_agent)
            
            if is_valid:
                logger.info(f"OTP validado exitosamente: {email} - {purpose}")
                return {
                    'success': True,
                    'otp': validated_otp,
                    'message': 'Código válido',
                    'user': validated_otp.user
                }
            else:
                return {
                    'success': False,
                    'otp': otp,
                    'message': error_message or 'Código inválido',
                    'user': otp.user
                }
                
        except Exception as e:
            logger.error(f"Error validando OTP: {str(e)}")
            return {
                'success': False,
                'otp': None,
                'message': 'Error interno del sistema',
                'user': None
            }
    
    @classmethod
    def resend_code(cls, email, purpose, request=None):
        """
        Reenvía un código OTP (genera uno nuevo)
        """
        # Buscar usuario si existe
        user = None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            pass
        
        return cls.generate_and_send(
            email=email,
            purpose=purpose,
            user=user,
            request=request
        )
    
    @classmethod
    def cleanup_expired_codes(cls):
        """
        Limpia códigos expirados (para tarea programada)
        """
        return OTP.objects.cleanup_expired()
    
    @classmethod
    def get_active_code_info(cls, email, purpose):
        """
        Obtiene información del código activo sin revelarlo
        """
        otp = OTP.objects.get_active_for_email(email, purpose)
        if otp:
            return {
                'exists': True,
                'expires_at': otp.expires_at,
                'time_remaining': otp.time_remaining,
                'attempts': otp.attempts,
                'max_attempts': cls.MAX_ATTEMPTS.get(purpose, 3)
            }
        return {'exists': False}
    
    @classmethod
    def _send_otp_email(cls, otp):
        """
        Envía el email con el código OTP con logos de Tuki embebidos
        """
        try:
            # Obtener template según el propósito
            template_map = {
                OTPPurpose.EVENT_CREATION: 'emails/otp_event_creation.html',
                OTPPurpose.LOGIN: 'emails/otp_login.html',
                OTPPurpose.TICKET_ACCESS: 'emails/otp_ticket_access.html',
                OTPPurpose.PASSWORD_RESET: 'emails/otp_password_reset.html',
                OTPPurpose.EMAIL_VERIFICATION: 'emails/otp_email_verification.html',
                OTPPurpose.ACCOUNT_CREATION: 'emails/otp_account_creation.html',
            }
            
            subject_map = {
                OTPPurpose.EVENT_CREATION: 'Código para crear tu evento - Tuki',
                OTPPurpose.LOGIN: 'Código de acceso - Tuki',
                OTPPurpose.TICKET_ACCESS: 'Accede a tus tickets - Tuki',
                OTPPurpose.PASSWORD_RESET: 'Recupera tu contraseña - Tuki',
                OTPPurpose.EMAIL_VERIFICATION: 'Verifica tu email - Tuki',
                OTPPurpose.ACCOUNT_CREATION: 'Completa tu registro - Tuki',
            }
            
            template = template_map.get(otp.purpose, 'emails/otp_generic.html')
            subject = subject_map.get(otp.purpose, 'Tu código de verificación - Tuki')
            
            # Contexto para el template
            context = {
                'otp': otp,
                'code': otp.code,
                'email': otp.email,
                'purpose_display': otp.get_purpose_display(),
                'expires_at': otp.expires_at,
                'time_remaining_minutes': int(otp.time_remaining.total_seconds() // 60),
            }
            
            # Renderizar email HTML
            html_message = render_to_string(template, context)
            
            # Crear email con soporte para attachments
            email = EmailMultiAlternatives(
                subject=subject,
                body=f'Tu código de verificación es: {otp.code}\n\nEste código expira en {int(otp.time_remaining.total_seconds() // 60)} minutos.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[otp.email]
            )
            
            # Adjuntar versión HTML
            email.attach_alternative(html_message, "text/html")
            
            # Adjuntar logo como imagen inline (CID)
            # Logo negro para el header
            logo_negro_path = os.path.join(settings.BASE_DIR, 'static/images/logos/logo-negro.png')
            if os.path.exists(logo_negro_path):
                with open(logo_negro_path, 'rb') as logo_file:
                    logo_negro = MIMEImage(logo_file.read())
                    logo_negro.add_header('Content-ID', '<logo_negro>')
                    logo_negro.add_header('Content-Disposition', 'inline', filename='logo-negro.png')
                    email.attach(logo_negro)
            
            # Enviar email
            email.send(fail_silently=False)
            
            logger.info(f"📧 [OTP EMAIL] Sent OTP email for purpose {otp.purpose} to {otp.email}")
            return True
            
        except Exception as e:
            logger.error(f"Error enviando email OTP: {str(e)}")
            return False
    
    @classmethod
    def _get_client_ip(cls, request):
        """
        Obtiene la IP real del cliente
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @classmethod
    def _log_attempt(cls, otp, attempted_code, is_successful, ip_address, user_agent):
        """
        Registra un intento de validación
        """
        if otp:
            try:
                OTPAttempt.objects.create(
                    otp=otp,
                    attempted_code=attempted_code,
                    is_successful=is_successful,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
            except Exception as e:
                logger.error(f"Error logging OTP attempt: {str(e)}")


class OTPEmailService:
    """
    Servicio especializado para diferentes tipos de emails OTP
    """
    
    @staticmethod
    def send_event_creation_otp(email, code, event_data=None):
        """Email para creación de evento"""
        context = {
            'code': code,
            'event_title': event_data.get('title', 'tu evento') if event_data else 'tu evento',
            'email': email
        }
        return OTPEmailService._send_templated_email(
            'emails/otp_event_creation.html',
            'Código para crear tu evento - Tuki',
            email,
            context
        )
    
    @staticmethod
    def send_login_otp(email, code, user_name=None):
        """Email para login"""
        context = {
            'code': code,
            'user_name': user_name or email.split('@')[0],
            'email': email
        }
        return OTPEmailService._send_templated_email(
            'emails/otp_login.html',
            'Tu código de acceso - Tuki',
            email,
            context
        )
    
    @staticmethod
    def _send_templated_email(template, subject, email, context):
        """Método helper para enviar emails con template"""
        try:
            html_message = render_to_string(template, context)
            
            send_mail(
                subject=subject,
                message=f'Tu código de verificación es: {context["code"]}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html_message,
                fail_silently=False
            )
            return True
        except Exception as e:
            logger.error(f"Error sending templated email: {str(e)}")
            return False
