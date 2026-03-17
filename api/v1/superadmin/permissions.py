"""
SuperAdmin Permissions - Enterprise Security

Clases de permisos para proteger todos los endpoints de SuperAdmin.
Solo usuarios autenticados con is_superuser=True pueden acceder.

401 = not authenticated or invalid token; 403 = authenticated but not superuser.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotAuthenticated, PermissionDenied


class IsSuperUser(IsAuthenticated):
    """
    Permiso que solo permite acceso a superusers autenticados.
    401 si no hay token o es inválido; 403 si está autenticado pero no es superuser.
    """

    message = 'Se requiere autenticación como superusuario para acceder a este recurso.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated('Credenciales no proporcionadas o inválidas.')
        if not request.user.is_superuser:
            raise PermissionDenied('No tiene permisos de superusuario.')
        return True


class IsSuperUserOrReadOnly(IsAuthenticated):
    """
    Permiso que permite lectura a usuarios autenticados,
    pero escritura solo a superusers. 401 si no autenticado; 403 si sin permiso.
    """
    message = 'Se requiere autenticación como superusuario para modificar este recurso.'
    SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated('Credenciales no proporcionadas o inválidas.')
        if request.method in self.SAFE_METHODS:
            return True
        if not request.user.is_superuser:
            raise PermissionDenied('No tiene permisos de superusuario para esta acción.')
        return True
