"""Permissions for terminal app. 401 = not authenticated; 403 = no terminal admin role."""

from rest_framework import permissions
from rest_framework.exceptions import NotAuthenticated, PermissionDenied


class IsTerminalAdmin(permissions.BasePermission):
    """Permission to check if user is a terminal admin or superadmin."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated('Credenciales no proporcionadas o inválidas.')
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'role') and request.user.role in ['terminal_admin', 'superadmin']:
            return True
        if request.user.is_staff:
            return True
        raise PermissionDenied('No tiene permisos de administrador del terminal.')

