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
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.contrib.auth import login, logout
from django.shortcuts import get_object_or_404

from .models import User, Profile, ProfilePhoto, Interest, ProfileInterest, DeviceToken
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer,
    UserSerializer, ProfileSerializer, ProfileUpdateSerializer,
    ProfilePhotoUploadSerializer, InterestSerializer
)
from apps.common.pagination import StandardResultsSetPagination


from django.utils import timezone
from django.db.models import Exists, OuterRef, Q
from .models import Story, StoryView
from .serializers import StorySerializer, StoryCreateSerializer, StoryViewerSerializer


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
    serializer_class = UserLoginSerializer 

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
    lookup_field = 'id'

    def get_queryset(self):
        """
        Return only active users with completed profiles.
        """
        return (
            User.objects.filter(is_active=True)
            .select_related('profile')
            .prefetch_related('profile__photos', 'profile__interests__interest')
            .distinct()
        )

    @action(detail=True, methods=['get'], url_path='detail')
    def public_profile(self, request, id=None):
        """
        Get another user's public profile.
        
        GET /api/users/{user_uuid}/detail/
        """
        try:
            user = self.get_object()
            profile = user.profile
            
            # Get primary photo
            primary_photo = profile.photos.filter(is_primary=True).first()
            if not primary_photo:
                primary_photo = profile.photos.first()
            
            photo_url = None
            if primary_photo:
                photo_url = request.build_absolute_uri(primary_photo.image.url)
            
            # Get interests
            interests = [pi.interest.name for pi in profile.interests.all()[:10]]
            
            return Response({
                'id': str(user.id),
                'username': user.username,
                'age': profile.age,
                'city': profile.city,
                'country': profile.country,
                'bio': profile.bio,
                'gender': profile.get_gender_display(),
                'relationship_goal': profile.get_relationship_goal_display(),
                'photo_url': photo_url,
                'interests': interests,
            })
            
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
    @action(detail=True, methods=['get'], url_path='profile')
    def get_user_profile(self, request, id=None):
            """
            Get detailed profile of another user.
            Also check if users are matched.
            
            GET /api/users/{user_id}/profile/
            """
            try:
                user = self.get_object()
                profile = user.profile
                
                # Check if users are matched
                from apps.matching.models import Match
                is_matched = Match.objects.filter(
                    user=request.user,
                    matched_user=user,
                    is_mutual=True
                ).exists()
                
                # Get primary photo
                primary_photo = profile.photos.filter(is_primary=True).first()
                if not primary_photo:
                    primary_photo = profile.photos.first()
                
                photo_url = None
                if primary_photo:
                    photo_url = request.build_absolute_uri(primary_photo.image.url)
                
                # Get all photos
                all_photos = []
                for photo in profile.photos.all()[:6]:
                    all_photos.append(request.build_absolute_uri(photo.image.url))
                
                # Get interests
                interests = [pi.interest.name for pi in profile.interests.all()]
                
                return Response({
                    'id': str(user.id),
                    'username': user.username,
                    'age': profile.age,
                    'city': profile.city,
                    'country': profile.country,
                    'bio': profile.bio,
                    'gender': profile.get_gender_display() if profile.gender else '',
                    'relationship_goal': profile.get_relationship_goal_display() if profile.relationship_goal else '',
                    'photo_url': photo_url,
                    'all_photos': all_photos,
                    'interests': interests,
                    'is_matched': is_matched,  # ← Important!
                })
                
            except User.DoesNotExist:
                return Response({
                    'error': 'User not found'
                }, status=status.HTTP_404_NOT_FOUND)

# ============================================================================
# PROFILE VIEWSET
# ============================================================================
class ProfileViewSet(viewsets.GenericViewSet):
    """
    Manage the authenticated user's profile.
    - View, update, upload/delete photo, add/remove interests.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        """
        Get or create the profile for the current user.
        """
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

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

    @action(detail=False, methods=['put', 'patch'], url_path='update')
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
                "is_primary": photo.is_primary
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
    
# ============================================================================
# INTEREST VIEWSET (Read-only)
# ============================================================================
class InterestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing available interests.
    """
    queryset = Interest.objects.all().order_by('name')
    serializer_class = InterestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None 

#======= Fire base notifications push
class DeviceTokenViewSet(viewsets.ViewSet):
    """
    Manage device tokens for push notifications.
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def register(self, request):
        """
        Register or update device token.
        
        POST /api/users/device-token/
        Body: {
            "token": "ExponentPushToken[xxx]",
            "platform": "ios" or "android",
            "device_type": "iPhone 13"
        }
        """
        token = request.data.get('token')
        platform = request.data.get('platform')
        device_type = request.data.get('device_type', '')
        
        if not token or not platform:
            return Response({
                'error': 'Token and platform are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create or update token
        device_token, created = DeviceToken.objects.update_or_create(
            user=request.user,
            token=token,
            defaults={
                'platform': platform,
                'device_type': device_type,
                'is_active': True
            }
        )
        
        return Response({
            'message': 'Token registered successfully',
            'created': created
        }, status=status.HTTP_200_OK)
    

#===========================================================================
class StoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing stories.
    
    Endpoints:
    - GET /api/stories/ - List all active stories
    - POST /api/stories/ - Create new story
    - GET /api/stories/{id}/ - Get specific story
    - DELETE /api/stories/{id}/ - Delete own story
    - GET /api/stories/my_stories/ - Get current user's stories
    - POST /api/stories/{id}/mark_viewed/ - Mark story as viewed
    - GET /api/stories/{id}/viewers/ - Get list of viewers
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = StorySerializer
    
    def get_queryset(self):
        """
        Get active stories (not expired).
        Exclude stories from current user unless accessing my_stories.
        """
        now = timezone.now()
        
        # Get active stories
        queryset = Story.objects.filter(
            expires_at__gt=now
        ).select_related(
            'user',
            'user__profile'
        ).prefetch_related(
            'user__profile__photos'
        )
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoryCreateSerializer
        return StorySerializer
    
    def list(self, request):
        """
        Get stories from all users grouped by user.
        Returns users who have active stories.
        """
        now = timezone.now()
        
        # Get all users who have active stories
        users_with_stories = User.objects.filter(
            stories__expires_at__gt=now
        ).distinct().select_related('profile').prefetch_related('profile__photos')
        
        results = []
        for user in users_with_stories:
            # Get user's active stories
            user_stories = Story.objects.filter(
                user=user,
                expires_at__gt=now
            ).order_by('-created_at')
            
            # Check if any story is unviewed by current user
            has_unviewed = user_stories.exclude(
                viewers__viewer=request.user
            ).exists()
            
            # Get user photo
            primary_photo = user.profile.photos.filter(is_primary=True).first()
            user_photo = None
            if primary_photo:
                user_photo = request.build_absolute_uri(primary_photo.image.url)
            
            # Serialize stories
            stories_data = StorySerializer(
                user_stories,
                many=True,
                context={'request': request}
            ).data
            
            results.append({
                'user_id': str(user.id),
                'username': user.username,
                'user_photo': user_photo,
                'has_unviewed': has_unviewed,
                'story_count': user_stories.count(),
                'stories': stories_data
            })
        
        # Sort: unviewed first, then by most recent story
        results.sort(key=lambda x: (not x['has_unviewed'], -len(x['stories'])))
        
        return Response({
            'count': len(results),
            'results': results
        })
    
    def create(self, request):
        """Create a new story."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Create story for current user
        story = serializer.save(user=request.user)
        
        # Return full story data
        response_serializer = StorySerializer(story, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    def destroy(self, request, pk=None):
        """Delete own story."""
        story = self.get_object()
        
        # Check if story belongs to current user
        if story.user != request.user:
            return Response(
                {'error': 'You can only delete your own stories'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        story.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=False, methods=['get'])
    def my_stories(self, request):
        """Get current user's active stories."""
        now = timezone.now()
        
        stories = Story.objects.filter(
            user=request.user,
            expires_at__gt=now
        ).order_by('-created_at')
        
        serializer = self.get_serializer(stories, many=True)
        
        return Response({
            'count': stories.count(),
            'results': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def mark_viewed(self, request, pk=None):
        """Mark story as viewed by current user."""
        story = self.get_object()
        
        # Don't count own views
        if story.user == request.user:
            return Response({'message': 'Cannot view own story'})
        
        # Create or get view record
        view, created = StoryView.objects.get_or_create(
            story=story,
            viewer=request.user
        )
        
        if created:
            # Increment view count
            story.increment_views()
        
        return Response({
            'message': 'Story marked as viewed',
            'view_count': story.view_count
        })
    
    @action(detail=True, methods=['get'])
    def viewers(self, request, pk=None):
        """Get list of users who viewed this story."""
        story = self.get_object()
        
        # Only owner can see viewers
        if story.user != request.user:
            return Response(
                {'error': 'You can only view viewers of your own stories'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        viewers = StoryView.objects.filter(story=story).select_related('viewer', 'viewer__profile')
        serializer = StoryViewerSerializer(viewers, many=True, context={'request': request})
        
        return Response({
            'count': viewers.count(),
            'results': serializer.data
        })