"""
🚀 ENTERPRISE PERMISSIONS

Permisos personalizados para el sistema de migración.
"""

from rest_framework import permissions
from django.utils import timezone
from .models import MigrationToken


class HasMigrationToken(permissions.BasePermission):
    """
    Permiso que verifica que el request tenga un MigrationToken válido.
    
    El token debe enviarse en el header Authorization:
        Authorization: MigrationToken abc-123-xyz-456
    """
    
    message = 'Token de migración inválido o expirado'
    
    def has_permission(self, request, view):
        """
        Verifica que el request tenga un token válido.
        """
        # Obtener token del header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header.startswith('MigrationToken '):
            return False
        
        token_value = auth_header.replace('MigrationToken ', '').strip()
        
        if not token_value:
            return False
        
        # Buscar token en BD
        try:
            token = MigrationToken.objects.get(token=token_value)
        except MigrationToken.DoesNotExist:
            return False
        
        # Verificar validez
        if not token.is_valid:
            return False
        
        # Verificar IP si está configurado
        if token.allowed_ips:
            client_ip = self.get_client_ip(request)
            if client_ip not in token.allowed_ips:
                return False
        
        # Verificar dominio si está configurado
        if token.allowed_domains:
            origin = request.META.get('HTTP_ORIGIN', '')
            referer = request.META.get('HTTP_REFERER', '')
            
            domain_match = False
            for allowed_domain in token.allowed_domains:
                if allowed_domain in origin or allowed_domain in referer:
                    domain_match = True
                    break
            
            if not domain_match:
                return False
        
        # Marcar token como usado
        token.mark_used(ip_address=self.get_client_ip(request))
        
        # Guardar token en request para uso posterior
        request.migration_token = token
        
        return True
    
    def get_client_ip(self, request):
        """Obtiene la IP del cliente."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class IsSuperUserOrHasMigrationToken(permissions.BasePermission):
    """
    Permiso que permite acceso a superusers o con MigrationToken válido.
    """
    
    def has_permission(self, request, view):
        # Verificar si es superuser
        if request.user and request.user.is_authenticated and request.user.is_superuser:
            return True
        
        # Si no, verificar token
        has_token_perm = HasMigrationToken()
        return has_token_perm.has_permission(request, view)


class CanExport(permissions.BasePermission):
    """
    Permiso para exportar datos.
    Requiere superuser o token con permisos 'read' o 'admin'.
    """
    
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated and request.user.is_superuser:
            return True
        
        if hasattr(request, 'migration_token'):
            token = request.migration_token
            return token.permissions in ['read', 'read_write', 'admin']
        
        return False


class CanImport(permissions.BasePermission):
    """
    Permiso para importar datos.
    Requiere superuser o token con permisos 'write' o 'admin'.
    """
    
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated and request.user.is_superuser:
            return True
        
        if hasattr(request, 'migration_token'):
            token = request.migration_token
            return token.permissions in ['write', 'read_write', 'admin']
        
        return False
