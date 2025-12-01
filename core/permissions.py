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
        """Check if user has organizer permissions."""
        print(f"DEBUG - IsOrganizer.has_permission - User ID: {request.user.id if request.user.is_authenticated else 'Anonymous'}")
        
        if not request.user.is_authenticated:
            print("DEBUG - IsOrganizer.has_permission - FAIL: User not authenticated")
            return False
            
        if not hasattr(request.user, 'organizer_roles'):
            print("DEBUG - IsOrganizer.has_permission - FAIL: User has no organizer_roles attribute")
            return False
        
        has_role = request.user.organizer_roles.exists()
        print(f"DEBUG - IsOrganizer.has_permission - User has organizer role: {has_role}")
        return has_role
    
    def has_object_permission(self, request, view, obj):
        """Check if object belongs to the user's organizer."""
        print(f"DEBUG - IsOrganizer.has_object_permission - User ID: {request.user.id if request.user.is_authenticated else 'Anonymous'}")
        print(f"DEBUG - IsOrganizer.has_object_permission - Object: {obj}")
        print(f"DEBUG - IsOrganizer.has_object_permission - Object type: {type(obj)}")
        
        if not request.user.is_authenticated:
            print("DEBUG - IsOrganizer.has_object_permission - FAIL: User not authenticated")
            return False
        
        if not hasattr(request.user, 'organizer_roles'):
            print("DEBUG - IsOrganizer.has_object_permission - FAIL: User has no organizer_roles attribute")
            return False
        
        # Check if the object has organizer attribute
        if hasattr(obj, 'organizer'):
            # Get the organizer from the object
            has_permission = request.user.organizer_roles.filter(organizer=obj.organizer).exists()
            print(f"DEBUG - IsOrganizer.has_object_permission - Organizer permission check result: {has_permission}")
            if not has_permission:
                print(f"DEBUG - IsOrganizer.has_object_permission - FAIL: User has no role in this organizer")
            return has_permission
        
        # Check if the object has event attribute (for event-related objects)
        if hasattr(obj, 'event') and hasattr(obj.event, 'organizer'):
            has_permission = request.user.organizer_roles.filter(organizer=obj.event.organizer).exists()
            print(f"DEBUG - IsOrganizer.has_object_permission - Event organizer permission check result: {has_permission}")
            return has_permission
        
        # Check if the object is an event
        if hasattr(obj, 'organizer'):
            has_permission = request.user.organizer_roles.filter(organizer=obj.organizer).exists()
            print(f"DEBUG - IsOrganizer.has_object_permission - Event organizer permission check result: {has_permission}")
            return has_permission
        
        print(f"DEBUG - IsOrganizer.has_object_permission - FAIL: Object has no organizer or event attribute")
        return False


class IsOrganizerAdmin(permissions.BasePermission):
    """Permission to check if user is an organizer admin."""
    
    def has_permission(self, request, view):
        """Check if user has admin permissions for any organizer."""
        if not request.user.is_authenticated:
            return False
        
        if not hasattr(request.user, 'organizer_roles'):
            return False
        
        return request.user.organizer_roles.filter(is_admin=True).exists()
    
    def has_object_permission(self, request, view, obj):
        """Check if user has admin permissions for the object's organizer."""
        if not request.user.is_authenticated:
            return False
        
        if not hasattr(request.user, 'organizer_roles'):
            return False
        
        # Check if the object has organizer attribute
        if hasattr(obj, 'organizer'):
            return request.user.organizer_roles.filter(
                organizer=obj.organizer,
                is_admin=True
            ).exists()
        
        # Check if the object has event attribute
        if hasattr(obj, 'event') and hasattr(obj.event, 'organizer'):
            return request.user.organizer_roles.filter(
                organizer=obj.event.organizer,
                is_admin=True
            ).exists()
        
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
        
        if not request.user.is_authenticated:
            return False
            
        try:
            organizer_user = OrganizerUser.objects.get(user=request.user)
            
            # First, check if the object belongs to the organizer
            if hasattr(obj, 'organizer'):
                if obj.organizer != organizer_user.organizer:
                    return False
            
            has_module = organizer_user.organizer.has_events_module
            can_manage = organizer_user.can_manage_events
            
            return has_module and can_manage
            
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
            has_module = organizer_user.organizer.has_experience_module
            can_manage = organizer_user.can_manage_experiences if hasattr(organizer_user, 'can_manage_experiences') else True
            
            return has_module and can_manage
            
        except OrganizerUser.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"HasExperienceModule.has_permission - Error: {str(e)}")
            return False
    
    def has_object_permission(self, request, view, obj):
        """Check if organizer has the experience module activated for this object."""
        from apps.organizers.models import OrganizerUser
        
        if not request.user.is_authenticated:
            return False
        
        try:
            organizer_user = OrganizerUser.objects.get(user=request.user)
            has_module = organizer_user.organizer.has_experience_module
            
            if not has_module:
                return False
            
            # Check if object belongs to organizer
            if hasattr(obj, 'organizer'):
                return obj.organizer == organizer_user.organizer
            if hasattr(obj, 'experience') and hasattr(obj.experience, 'organizer'):
                return obj.experience.organizer == organizer_user.organizer
            
            return False
            
        except OrganizerUser.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"HasExperienceModule.has_object_permission - Error: {str(e)}")
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


class IsTicketValidator(permissions.BasePermission):
    """Permission to check if user is a ticket validator."""
    
    def has_permission(self, request, view):
        """Check if user is a ticket validator."""
        return (
            request.user.is_authenticated and 
            request.user.groups.filter(name='ticket_validators').exists()
        ) 