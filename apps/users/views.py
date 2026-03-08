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

from .models import User, Profile, ProfilePhoto, Interest, ProfileInterest
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer,
    UserSerializer, ProfileSerializer, ProfileUpdateSerializer,
    ProfilePhotoUploadSerializer, InterestSerializer
)
from apps.common.pagination import StandardResultsSetPagination


# ============================================================================
# AUTH VIEWSET
# ============================================================================
class AuthViewSet(viewsets.GenericViewSet):
    """
    ViewSet for authentication operations.
    """
    permission_classes = [AllowAny]
    serializer_class = UserLoginSerializer 

    def get_serializer_class(self):
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
            'message': 'Utilisateur inscrit avec succès.',
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
            'message': 'Connexion réussie.',
            'user': UserSerializer(user, context={'request': request}).data,
            'token': token.key
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        request.user.auth_token.delete()
        logout(request)
        return Response({'message': 'Déconnexion réussie.'}, status=status.HTTP_200_OK)

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
        return (
            User.objects.filter(is_active=True)
            .select_related('profile')
            .prefetch_related('profile__photos', 'profile__interests__interest')
            .distinct()
        )

    @action(detail=True, methods=['get'], url_path='detail')
    def public_profile(self, request, id=None):
        try:
            user = self.get_object()
            profile = user.profile
            
            primary_photo = profile.photos.filter(is_primary=True).first() or profile.photos.first()
            photo_url = request.build_absolute_uri(primary_photo.image.url) if primary_photo else None
            interests = [pi.interest.name for pi in profile.interests.all()[:10]]
            
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
                'interests': interests,
            })
            
        except User.DoesNotExist:
            return Response({'error': 'Utilisateur introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        
    @action(detail=True, methods=['get'], url_path='profile')
    def get_user_profile(self, request, id=None):
            try:
                user = self.get_object()
                profile = user.profile
                
                # Check if users are matched
                from apps.matching.models import Match
                is_matched = Match.objects.filter(
                    user=request.user, matched_user=user, is_mutual=True
                ).exists()
                
                primary_photo = profile.photos.filter(is_primary=True).first() or profile.photos.first()
                photo_url = request.build_absolute_uri(primary_photo.image.url) if primary_photo else None
                all_photos = [request.build_absolute_uri(photo.image.url) for photo in profile.photos.all()[:6]]
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
                    'is_matched': is_matched,
                })
                
            except User.DoesNotExist:
                return Response({'error': 'Utilisateur introuvable.'}, status=status.HTTP_404_NOT_FOUND)


# ============================================================================
# PROFILE VIEWSET
# ============================================================================
class ProfileViewSet(viewsets.GenericViewSet):
    """
    Manage the authenticated user's profile.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    @action(detail=False, methods=['get'])
    def me(self, request):
        profile = self.get_object()
        return Response(ProfileSerializer(profile, context={'request': request}).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['put', 'patch'], url_path='update')
    def update_profile(self, request):
        profile = self.get_object()
        serializer = ProfileUpdateSerializer(
            profile, data=request.data, partial=(request.method == 'PATCH'), context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "message": "Profil mis à jour avec succès.",
            "profile": ProfileSerializer(profile, context={'request': request}).data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def upload_photo(self, request):
        profile = self.get_object()
        serializer = ProfilePhotoUploadSerializer(
            data=request.data, context={'request': request, 'profile': profile}
        )
        serializer.is_valid(raise_exception=True)
        photo = serializer.save()

        return Response({
            "message": "Photo téléchargée avec succès.",
            "photo": {
                "id": photo.id,
                "url": request.build_absolute_uri(photo.image.url),
                "is_primary": photo.is_primary
            }
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['delete'])
    def delete_photo(self, request):
        photo_id = request.query_params.get('photo_id')
        if not photo_id:
            return Response({"error": "L'ID de la photo est requis."}, status=status.HTTP_400_BAD_REQUEST)

        profile = self.get_object()
        try:
            photo = ProfilePhoto.objects.get(id=photo_id, profile=profile)
            photo.delete()
            profile.calculate_completion_percentage()
            return Response({"message": "Photo supprimée avec succès."}, status=status.HTTP_200_OK)
        except ProfilePhoto.DoesNotExist:
            return Response({"error": "Photo introuvable."}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def add_interest(self, request):
        interest_id = request.data.get('interest_id')
        passion_level = request.data.get('passion_level', 3)
        if not interest_id:
            return Response({"error": "L'ID du centre d'intérêt est requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            interest = Interest.objects.get(id=interest_id)
            profile = self.get_object()
            profile_interest, created = ProfileInterest.objects.update_or_create(
                profile=profile, interest=interest, defaults={"passion_level": passion_level}
            )
            profile.calculate_completion_percentage()
            return Response({
                "message": "Centre d'intérêt ajouté avec succès.",
                "interest": {"id": interest.id, "name": interest.name, "passion_level": passion_level}
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        except Interest.DoesNotExist:
            return Response({"error": "Centre d'intérêt introuvable."}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['delete'])
    def remove_interest(self, request):
        interest_id = request.query_params.get('interest_id')
        if not interest_id:
            return Response({"error": "L'ID du centre d'intérêt est requis."}, status=status.HTTP_400_BAD_REQUEST)

        profile = self.get_object()
        deleted, _ = ProfileInterest.objects.filter(profile=profile, interest_id=interest_id).delete()

        if deleted:
            profile.calculate_completion_percentage()
            return Response({"message": "Centre d'intérêt retiré avec succès."}, status=status.HTTP_200_OK)
        return Response({"error": "Centre d'intérêt introuvable dans le profil."}, status=status.HTTP_404_NOT_FOUND)
    
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