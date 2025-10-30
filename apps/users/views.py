"""
User Views
===========
Handles:
- Authentication (register, login, logout, me)
- User profile viewing
- Profile management (update, photos, interests)
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import login, logout

from .models import User, Profile, ProfilePhoto, Interest, ProfileInterest
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer,
    UserSerializer, ProfileSerializer, ProfileUpdateSerializer,
    ProfilePhotoUploadSerializer
)
from apps.common.pagination import StandardResultsSetPagination


# ============================================================================
# AUTH VIEWSET
# ============================================================================
class AuthViewSet(viewsets.GenericViewSet):
    """
    ViewSet for authentication operations.
    
    Endpoints:
    - POST /api/auth/register/ - Register new user
    - POST /api/auth/login/ - Login user
    - POST /api/auth/logout/ - Logout user
    - GET /api/auth/me/ - Get current user info
    """

    permission_classes = [AllowAny]
    serializer_class = UserLoginSerializer  # Default fallback

    def get_serializer_class(self):
        """
        Return different serializers depending on the current action.
        """
        if self.action == 'register':
            return UserRegistrationSerializer
        elif self.action == 'login':
            return UserLoginSerializer
        return UserSerializer

    @action(detail=False, methods=['post'])
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        login(request, user)

        return Response({
            'message': 'User registered successfully.',
            'user': UserSerializer(user, context={'request': request}).data,
            'token': token.key
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def login(self, request):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        login(request, user)

        if hasattr(user, 'update_last_active'):
            user.update_last_active()

        return Response({
            'message': 'User logged in successfully.',
            'user': UserSerializer(user, context={'request': request}).data,
            'token': token.key
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        request.user.auth_token.delete()
        logout(request)
        return Response({'message': 'User logged out successfully.'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        user = request.user
        return Response({
            'user': UserSerializer(user, context={'request': request}).data
        }, status=status.HTTP_200_OK)

# ============================================================================
# USER VIEWSET (Read-only)
# ============================================================================
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public user profiles (read-only).
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    lookup_field = 'uuid'

    def get_queryset(self):
        """
        Return only active users with completed profiles.
        """
        return (
            User.objects.filter(is_active=True)
            .select_related('profile')
            .prefetch_related('profile__photos', 'profile__interests')
            .distinct()
        )


# ============================================================================
# PROFILE VIEWSET
# ============================================================================
class ProfileViewSet(viewsets.GenericViewSet):
    """
    Manage the authenticated user's profile.
    - View, update, upload/delete photo, add/remove interests.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]  # For photo uploads

    def get_object(self):
        return self.request.user.profile

    @action(detail=False, methods=['get'])
    def me(self, request):
        """
        Get current user's profile.
        """
        profile = self.get_object()
        return Response(
            ProfileSerializer(profile, context={'request': request}).data,
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['put', 'patch'])
    def update_profile(self, request):
        """
        Update user's profile details.
        """
        profile = self.get_object()
        serializer = ProfileUpdateSerializer(
            profile,
            data=request.data,
            partial=(request.method == 'PATCH'),
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "message": "Profile updated successfully",
            "profile": ProfileSerializer(profile, context={'request': request}).data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def upload_photo(self, request):
        """
        Upload profile photo.
        """
        profile = self.get_object()
        serializer = ProfilePhotoUploadSerializer(
            data=request.data,
            context={'request': request, 'profile': profile}
        )
        serializer.is_valid(raise_exception=True)
        photo = serializer.save()

        return Response({
            "message": "Photo uploaded successfully",
            "photo": {
                "id": photo.id,
                "url": request.build_absolute_uri(photo.image.url),
                "is_primary": photo.is_primary,
                "order": photo.order
            }
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['delete'])
    def delete_photo(self, request):
        """
        Delete a photo from user's profile.
        """
        photo_id = request.query_params.get('photo_id')
        if not photo_id:
            return Response({"error": "photo_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        profile = self.get_object()
        try:
            photo = ProfilePhoto.objects.get(id=photo_id, profile=profile)
            photo.delete()
            profile.calculate_completion_percentage()
            return Response({"message": "Photo deleted successfully"}, status=status.HTTP_200_OK)
        except ProfilePhoto.DoesNotExist:
            return Response({"error": "Photo not found"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def add_interest(self, request):
        """
        Add an interest to user's profile.
        """
        interest_id = request.data.get('interest_id')
        passion_level = request.data.get('passion_level', 3)
        if not interest_id:
            return Response({"error": "interest_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            interest = Interest.objects.get(id=interest_id)
            profile = self.get_object()
            profile_interest, created = ProfileInterest.objects.update_or_create(
                profile=profile,
                interest=interest,
                defaults={"passion_level": passion_level}
            )
            profile.calculate_completion_percentage()
            return Response({
                "message": "Interest added successfully",
                "interest": {
                    "id": interest.id,
                    "name": interest.name,
                    "passion_level": passion_level
                }
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        except Interest.DoesNotExist:
            return Response({"error": "Interest not found"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['delete'])
    def remove_interest(self, request):
        """
        Remove an interest from user's profile.
        """
        interest_id = request.query_params.get('interest_id')
        if not interest_id:
            return Response({"error": "interest_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        profile = self.get_object()
        deleted, _ = ProfileInterest.objects.filter(profile=profile, interest_id=interest_id).delete()

        if deleted:
            profile.calculate_completion_percentage()
            return Response({"message": "Interest removed successfully"}, status=status.HTTP_200_OK)
        return Response({"error": "Interest not found in profile"}, status=status.HTTP_404_NOT_FOUND)
