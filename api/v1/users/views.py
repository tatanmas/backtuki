"""Views for users API."""

from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, filters
from drf_spectacular.utils import extend_schema

from core.permissions import IsSuperAdmin
from .serializers import UserSerializer, UserDetailSerializer

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint for users.
    """
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering_fields = ['email', 'date_joined', 'last_login']
    ordering = ['-date_joined']
    
    def get_queryset(self):
        """
        Get queryset based on permission.
        """
        # Admin can see all users
        if self.request.user.is_superuser:
            return User.objects.all()
        
        # Regular users can only see themselves
        return User.objects.filter(id=self.request.user.id)
    
    def get_serializer_class(self):
        """
        Return appropriate serializer class.
        """
        if self.action == 'retrieve':
            return UserDetailSerializer
        return UserSerializer
    
    def get_permissions(self):
        """
        Get permissions based on action.
        """
        if self.action == 'retrieve':
            return [permissions.IsAuthenticated()]
        elif self.action in ['list', 'create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsSuperAdmin()]
        return [permissions.IsAuthenticated()]
    
    @extend_schema(
        description="List all users. Only accessible by superadmins."
    )
    def list(self, request, *args, **kwargs):
        """
        List users.
        """
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        description="Get a specific user. Regular users can only retrieve their own profile."
    )
    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve a user.
        """
        return super().retrieve(request, *args, **kwargs) 