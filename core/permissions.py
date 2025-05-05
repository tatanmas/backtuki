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
        print(f"DEBUG - IsOrganizer.has_permission - User ID: {request.user.id if request.user.is_authenticated else 'Anonymous'}")
        print(f"DEBUG - IsOrganizer.has_permission - User authenticated: {request.user.is_authenticated}")
        print(f"DEBUG - IsOrganizer.has_permission - Has organizer_roles: {hasattr(request.user, 'organizer_roles')}")
        
        if not request.user.is_authenticated:
            print(f"DEBUG - IsOrganizer.has_permission - FAIL: User not authenticated")
            return False
            
        if not hasattr(request.user, 'organizer_roles'):
            print(f"DEBUG - IsOrganizer.has_permission - FAIL: User has no organizer_roles attribute")
            return False
        
        # Check if the user has any organizer roles
        has_roles = request.user.organizer_roles.exists()
        print(f"DEBUG - IsOrganizer.has_permission - User has organizer roles: {has_roles}")
        
        return has_roles
    
    def has_object_permission(self, request, view, obj):
        """Check if object belongs to the user's organizer tenant."""
        print(f"DEBUG - IsOrganizer.has_object_permission - User ID: {request.user.id if request.user.is_authenticated else 'Anonymous'}")
        print(f"DEBUG - IsOrganizer.has_object_permission - Object: {obj}")
        print(f"DEBUG - IsOrganizer.has_object_permission - Object type: {type(obj)}")
        
        if not request.user.is_authenticated:
            print("DEBUG - IsOrganizer.has_object_permission - FAIL: User not authenticated")
            return False
        
        if not hasattr(request.user, 'organizer_roles'):
            print("DEBUG - IsOrganizer.has_object_permission - FAIL: User has no organizer_roles attribute")
            return False
        
        # Check if the object has tenant_id attribute (uses TenantAwareModel)
        if hasattr(obj, 'tenant_id'):
            # Get the organizer from the tenant_id
            try:
                organizer = Organizer.objects.get(schema_name=obj.tenant_id)
                has_permission = request.user.organizer_roles.filter(organizer=organizer).exists()
                print(f"DEBUG - IsOrganizer.has_object_permission - Tenant permission check result: {has_permission}")
                if not has_permission:
                    print(f"DEBUG - IsOrganizer.has_object_permission - FAIL: User has no role in this tenant")
                return has_permission
            except Organizer.DoesNotExist:
                print(f"DEBUG - IsOrganizer.has_object_permission - FAIL: Organizer not found for tenant {obj.tenant_id}")
                return False
        
        # For organizer-specific objects, check if user has a role in that organizer
        if hasattr(obj, 'organizer'):
            print(f"DEBUG - IsOrganizer.has_object_permission - Checking organizer permission with object.organizer: {obj.organizer.id if obj.organizer else 'None'}")
            has_permission = request.user.organizer_roles.filter(organizer=obj.organizer).exists()
            print(f"DEBUG - IsOrganizer.has_object_permission - Organizer permission check result: {has_permission}")
            if not has_permission:
                print(f"DEBUG - IsOrganizer.has_object_permission - FAIL: User has no role in this organizer")
            return has_permission
        
        # If the object is an Organizer instance itself
        if isinstance(obj, Organizer):
            print(f"DEBUG - IsOrganizer.has_object_permission - Checking direct organizer permission: {obj.id}")
            has_permission = request.user.organizer_roles.filter(organizer=obj).exists()
            print(f"DEBUG - IsOrganizer.has_object_permission - Direct organizer permission check result: {has_permission}")
            if not has_permission:
                print(f"DEBUG - IsOrganizer.has_object_permission - FAIL: User has no role in this organizer")
            return has_permission
        
        print("DEBUG - IsOrganizer.has_object_permission - FAIL: No permission checks passed")
        return False


class HasEventModule(permissions.BasePermission):
    """Permission to check if organizer has the event module activated."""
    
    def has_permission(self, request, view):
        """Check if organizer has the event module activated."""
        from apps.organizers.models import OrganizerUser
        
        print(f"DEBUG - HasEventModule.has_permission - User ID: {request.user.id if request.user.is_authenticated else 'Anonymous'}")
        
        if not request.user.is_authenticated:
            print(f"DEBUG - HasEventModule.has_permission - FAIL: User not authenticated")
            return False
            
        try:
            organizer_user = OrganizerUser.objects.get(user=request.user)
            print(f"DEBUG - HasEventModule.has_permission - Found OrganizerUser: {organizer_user.id}")
            print(f"DEBUG - HasEventModule.has_permission - Organizer ID: {organizer_user.organizer.id}")
            print(f"DEBUG - HasEventModule.has_permission - has_events_module: {organizer_user.organizer.has_events_module}")
            print(f"DEBUG - HasEventModule.has_permission - can_manage_events: {organizer_user.can_manage_events}")
            
            # Check both conditions for permission
            has_module = organizer_user.organizer.has_events_module
            can_manage = organizer_user.can_manage_events
            
            if not has_module:
                print(f"DEBUG - HasEventModule.has_permission - FAIL: Organizer does not have events module")
            
            if not can_manage:
                print(f"DEBUG - HasEventModule.has_permission - FAIL: User cannot manage events")
                
            return has_module and can_manage
            
        except OrganizerUser.DoesNotExist:
            print(f"DEBUG - HasEventModule.has_permission - FAIL: OrganizerUser not found for User ID {request.user.id}")
            return False
        except Exception as e:
            print(f"DEBUG - HasEventModule.has_permission - FAIL: Unexpected error: {str(e)}")
            return False
    
    def has_object_permission(self, request, view, obj):
        """Check if organizer has the event module activated for this object."""
        from apps.organizers.models import OrganizerUser
        
        print(f"DEBUG - HasEventModule.has_object_permission - User ID: {request.user.id if request.user.is_authenticated else 'Anonymous'}")
        print(f"DEBUG - HasEventModule.has_object_permission - Object: {obj}")
        print(f"DEBUG - HasEventModule.has_object_permission - Object type: {type(obj)}")
        
        if not request.user.is_authenticated:
            print(f"DEBUG - HasEventModule.has_object_permission - FAIL: User not authenticated")
            return False
            
        try:
            organizer_user = OrganizerUser.objects.get(user=request.user)
            print(f"DEBUG - HasEventModule.has_object_permission - OrganizerUser found")
            
            # First, check if the object belongs to the organizer
            if hasattr(obj, 'organizer'):
                print(f"DEBUG - HasEventModule.has_object_permission - Checking object.organizer: {obj.organizer.id}")
                if obj.organizer != organizer_user.organizer:
                    print(f"DEBUG - HasEventModule.has_object_permission - FAIL: Object belongs to a different organizer")
                    return False
            
            has_module = organizer_user.organizer.has_events_module
            can_manage = organizer_user.can_manage_events
            
            print(f"DEBUG - HasEventModule.has_object_permission - has_events_module: {has_module}")
            print(f"DEBUG - HasEventModule.has_object_permission - can_manage_events: {can_manage}")
            
            if not has_module:
                print(f"DEBUG - HasEventModule.has_object_permission - FAIL: Organizer does not have events module")
            
            if not can_manage:
                print(f"DEBUG - HasEventModule.has_object_permission - FAIL: User cannot manage events")
            
            return has_module and can_manage
            
        except OrganizerUser.DoesNotExist:
            print(f"DEBUG - HasEventModule.has_object_permission - FAIL: OrganizerUser not found")
            return False


class HasAccommodationModule(permissions.BasePermission):
    """Permission to check if organizer has the accommodation module activated."""
    
    def has_permission(self, request, view):
        """Check if organizer has the accommodation module activated."""
        from apps.organizers.models import OrganizerUser
        
        if not request.user.is_authenticated:
            return False
            
        try:
            organizer_user = OrganizerUser.objects.get(user=request.user)
            return organizer_user.organizer.has_accommodation_module and organizer_user.can_manage_accommodations
        except OrganizerUser.DoesNotExist:
            return False


class HasExperienceModule(permissions.BasePermission):
    """Permission to check if organizer has the experience module activated."""
    
    def has_permission(self, request, view):
        """Check if organizer has the experience module activated."""
        from apps.organizers.models import OrganizerUser
        
        if not request.user.is_authenticated:
            return False
            
        try:
            organizer_user = OrganizerUser.objects.get(user=request.user)
            return organizer_user.organizer.has_experience_module and organizer_user.can_manage_experiences
        except OrganizerUser.DoesNotExist:
            return False


class IsTicketValidator(permissions.BasePermission):
    """Permission to check if user is a ticket validator."""
    
    def has_permission(self, request, view):
        """Check if user is a ticket validator."""
        return (
            request.user.is_authenticated and 
            request.user.groups.filter(name='ticket_validators').exists()
        ) 