"""Custom DRF permissions for the Tuki platform."""

from rest_framework import permissions


class IsSuperAdmin(permissions.BasePermission):
    """Permission to check if user is a super administrator."""
    
    def has_permission(self, request, view):
        """Check if user is a super administrator."""
        return request.user.is_authenticated and request.user.is_superuser


class IsOrganizer(permissions.BasePermission):
    """Permission to check if user is an organizer."""
    
    def has_permission(self, request, view):
        """Check if user is an organizer."""
        return request.user.is_authenticated and hasattr(request.user, 'organizer')
    
    def has_object_permission(self, request, view, obj):
        """Check if object belongs to the user's organizer tenant."""
        if not request.user.is_authenticated or not hasattr(request.user, 'organizer'):
            return False
        
        # Check if the object has tenant_id attribute (uses TenantAwareModel)
        if hasattr(obj, 'tenant_id'):
            return obj.tenant_id == request.user.organizer.schema_name
        return False


class HasEventModule(permissions.BasePermission):
    """Permission to check if organizer has the event module activated."""
    
    def has_permission(self, request, view):
        """Check if organizer has the event module activated."""
        return (
            request.user.is_authenticated and 
            hasattr(request.user, 'organizer') and 
            request.user.organizer.has_events_module
        )


class HasAccommodationModule(permissions.BasePermission):
    """Permission to check if organizer has the accommodation module activated."""
    
    def has_permission(self, request, view):
        """Check if organizer has the accommodation module activated."""
        return (
            request.user.is_authenticated and 
            hasattr(request.user, 'organizer') and 
            request.user.organizer.has_accommodation_module
        )


class HasExperienceModule(permissions.BasePermission):
    """Permission to check if organizer has the experience module activated."""
    
    def has_permission(self, request, view):
        """Check if organizer has the experience module activated."""
        return (
            request.user.is_authenticated and 
            hasattr(request.user, 'organizer') and 
            request.user.organizer.has_experience_module
        )


class IsTicketValidator(permissions.BasePermission):
    """Permission to check if user is a ticket validator."""
    
    def has_permission(self, request, view):
        """Check if user is a ticket validator."""
        return (
            request.user.is_authenticated and 
            request.user.groups.filter(name='ticket_validators').exists()
        ) 