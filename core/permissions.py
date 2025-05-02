"""Custom DRF permissions for the Tuki platform."""

from rest_framework import permissions
import logging
from apps.organizers.models import Organizer

logger = logging.getLogger(__name__)


class IsSuperAdmin(permissions.BasePermission):
    """Permission to check if user is a super administrator."""
    
    def has_permission(self, request, view):
        """Check if user is a super administrator."""
        return request.user.is_authenticated and request.user.is_superuser


class IsOrganizer(permissions.BasePermission):
    """Permission to check if user is an organizer."""
    
    def has_permission(self, request, view):
        """Check if user is an organizer."""
        logger.debug(f"Checking organizer permission for user: {request.user}")
        logger.debug(f"User authenticated: {request.user.is_authenticated}")
        logger.debug(f"Has organizer_roles: {hasattr(request.user, 'organizer_roles')}")
        
        return request.user.is_authenticated and hasattr(request.user, 'organizer_roles')
    
    def has_object_permission(self, request, view, obj):
        """Check if object belongs to the user's organizer tenant."""
        logger.debug(f"Checking object permission for user: {request.user}")
        logger.debug(f"Object: {obj}")
        
        if not request.user.is_authenticated or not hasattr(request.user, 'organizer_roles'):
            logger.debug("User not authenticated or no organizer roles")
            return False
        
        # Check if the object has tenant_id attribute (uses TenantAwareModel)
        if hasattr(obj, 'tenant_id'):
            # Get the organizer from the tenant_id
            try:
                organizer = Organizer.objects.get(schema_name=obj.tenant_id)
                has_permission = request.user.organizer_roles.filter(organizer=organizer).exists()
                logger.debug(f"Tenant permission check result: {has_permission}")
                return has_permission
            except Organizer.DoesNotExist:
                logger.debug("Organizer not found for tenant")
                return False
        
        # For organizer-specific objects, check if user has a role in that organizer
        if hasattr(obj, 'organizer'):
            has_permission = request.user.organizer_roles.filter(organizer=obj.organizer).exists()
            logger.debug(f"Organizer permission check result: {has_permission}")
            return has_permission
        
        # If the object is an Organizer instance itself
        if isinstance(obj, Organizer):
            has_permission = request.user.organizer_roles.filter(organizer=obj).exists()
            logger.debug(f"Direct organizer permission check result: {has_permission}")
            return has_permission
        
        logger.debug("No permission checks passed")
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