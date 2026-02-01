"""
SuperAdmin Permissions - Enterprise Security

Clases de permisos para proteger todos los endpoints de SuperAdmin.
Solo usuarios autenticados con is_superuser=True pueden acceder.
"""

from rest_framework.permissions import IsAuthenticated


class IsSuperUser(IsAuthenticated):
    """
    Permiso que solo permite acceso a superusers autenticados.
    
    Hereda de IsAuthenticated para verificar primero que el usuario
    esté autenticado con JWT, y luego verifica is_superuser.
    
    Usage:
        @permission_classes([IsSuperUser])
        def my_view(request):
            ...
            
        class MyViewSet(viewsets.ViewSet):
            permission_classes = [IsSuperUser]
    """
    
    message = 'Se requiere autenticación como superusuario para acceder a este recurso.'
    
    def has_permission(self, request, view):
        """
        Verifica que el usuario esté autenticado Y sea superuser.
        
        Returns:
            bool: True si el usuario está autenticado y es superuser
        """
        # Primero verificar autenticación (JWT válido)
        is_authenticated = super().has_permission(request, view)
        
        if not is_authenticated:
            return False
        
        # Luego verificar que sea superuser
        return request.user.is_superuser


class IsSuperUserOrReadOnly(IsAuthenticated):
    """
    Permiso que permite lectura a usuarios autenticados,
    pero escritura solo a superusers.
    
    Útil para endpoints que necesitan ser leídos por organizadores
    pero solo modificados por superadmins.
    """
    
    message = 'Se requiere autenticación como superusuario para modificar este recurso.'
    
    SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')
    
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        
        if not is_authenticated:
            return False
        
        # Permitir lectura a cualquier usuario autenticado
        if request.method in self.SAFE_METHODS:
            return True
        
        # Escritura solo para superusers
        return request.user.is_superuser
