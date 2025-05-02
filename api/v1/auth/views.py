"""Views for authentication API."""

from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from django_tenants.utils import schema_context
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    UserRegistrationSerializer,
    PasswordResetSerializer,
    PasswordResetConfirmSerializer,
    UserProfileSerializer,
    EmailTokenObtainPairSerializer,
)

User = get_user_model()


class EmailTokenObtainPairView(TokenObtainPairView):
    """
    Custom JWT token view that accepts email instead of username.
    """
    serializer_class = EmailTokenObtainPairSerializer


class RegistrationView(generics.CreateAPIView):
    """
    API view for user registration.
    """
    permission_classes = [AllowAny]
    serializer_class = UserRegistrationSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Generate JWT tokens for the user
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': serializer.data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    """
    API view for user logout.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # Get the refresh token from request
            refresh_token = request.data.get('refresh')
            
            if refresh_token:
                # Blacklist the refresh token
                token = RefreshToken(refresh_token)
                token.blacklist()
                
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetView(generics.GenericAPIView):
    """
    API view for requesting a password reset.
    """
    permission_classes = [AllowAny]
    serializer_class = PasswordResetSerializer
    
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            'detail': _('Password reset email has been sent.')
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(generics.GenericAPIView):
    """
    API view for confirming a password reset.
    """
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer
    
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            'detail': _('Password has been reset successfully.')
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def set_password_view(request):
    """
    API view for setting password during onboarding.
    This endpoint can be used to create a new user or set password for an existing user.
    """
    email = request.data.get('email')
    password = request.data.get('password')
    
    if not email or not password:
        return Response(
            {"detail": "Email and password are required."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Use the public schema for user operations
    with schema_context('public'):
        # Try to find an existing user with this email
        try:
            user = User.objects.get(email=email)
            # Update password for existing user
            user.set_password(password)
            user.save()
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'detail': 'Password set successfully for existing user.',
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
        
        except User.DoesNotExist:
            # Create new user
            user = User.objects.create_user(
                email=email,
                username=email,  # Use email as username
                password=password
            )
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            # Try to link user to organizer if an onboarding exists
            from apps.organizers.models import OrganizerOnboarding, OrganizerUser
            try:
                # Find onboarding with matching email
                onboarding = OrganizerOnboarding.objects.filter(contact_email=email, is_completed=True).first()
                if onboarding and onboarding.organizer:
                    # Create organizer user relation
                    OrganizerUser.objects.create(
                        user=user,
                        organizer=onboarding.organizer,
                        is_admin=True,
                        can_manage_events=True,
                        can_manage_accommodations=True,
                        can_manage_experiences=True,
                        can_view_reports=True,
                        can_manage_settings=True
                    )
            except Exception as e:
                print(f"Error linking user to organizer: {e}")
                # Continue execution even if linking fails
            
            return Response({
                'detail': 'New user created with password.',
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_201_CREATED)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    API view for retrieving and updating user profile.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer
    
    def get_object(self):
        return self.request.user 