"""Permissions for terminal app."""

from rest_framework import permissions


class IsTerminalAdmin(permissions.BasePermission):
    """Permission to check if user is a terminal admin or superadmin."""
    
    def has_permission(self, request, view):
        """Check if user has terminal admin permissions."""
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superadmin has access
        if request.user.is_superuser:
            return True
        
        # Check if user has terminal_admin role
        # Assuming User model has a role field or similar
        # Adjust based on your User model structure
        if hasattr(request.user, 'role'):
            return request.user.role in ['terminal_admin', 'superadmin']
        
        # Fallback: check if user is staff (for now)
        # For testing, allow staff users
        return request.user.is_staff

