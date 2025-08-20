"""Views for authentication API."""

from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from apps.organizers.models import OrganizerOnboarding

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
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    
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
    This endpoint creates a new user and completes the onboarding process.
    """
    email = request.data.get('email')
    password = request.data.get('password')
    onboarding_id = request.data.get('onboarding_id')

    if not email or not password:
        return Response(
            {"detail": "Email and password are required."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not onboarding_id:
        return Response(
            {"detail": "Onboarding ID is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Prevent creating duplicate users
    if User.objects.filter(email=email).exists():
        return Response(
            {"detail": "A user with this email already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )
        
    onboarding = get_object_or_404(OrganizerOnboarding, id=onboarding_id)

    with transaction.atomic():
        # Create the user
        user = User.objects.create_user(
            email=email,
            password=password,
            username=email, # Or generate a unique username
            is_active=True
        )

        # Complete the onboarding process, which creates the organizer and links the user
        organizer = onboarding.complete_onboarding(user=user)

    # Generate tokens for the new user
    refresh = RefreshToken.for_user(user)
    tokens = {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

    return Response(
        {
            "message": "User created and onboarding completed successfully.",
            "user_id": user.id,
            "organizer_id": organizer.id,
            "tokens": tokens
        },
        status=status.HTTP_201_CREATED
    )


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    API view for retrieving and updating user profile.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer
    
    def get_object(self):
        return self.request.user


class PasswordChangeView(APIView):
    """
    API view for changing user password.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        
        if not current_password or not new_password:
            return Response(
                {"detail": "Current password and new password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify current password
        if not user.check_password(current_password):
            return Response(
                {"detail": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Set new password and update last_password_change
        user.set_password(new_password)
        user.last_password_change = timezone.now()
        user.save()
        
        return Response(
            {"detail": "Password changed successfully."},
            status=status.HTTP_200_OK
        ) 