from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from apps.common.pagination import StandardResultsSetPagination
from apps.matching.services import MatchingService
from .models import Match
from apps.users.models import User, Profile
from apps.users.serializers import UserBriefSerializer, UserSerializer

class FeedViewSet(viewsets.ViewSet):
    """
    Simple feed endpoint to fetch potential matches.
    For now, just returns all users except the current user.
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        Get feed of potential matches.
        
        GET /api/feed/?limit=20
        """
        limit = int(request.query_params.get('limit', 20))
        current_user = request.user
        
        # Get all active users except current user
        # Filter by profile completion
        users = User.objects.filter(
            is_active=True
        ).exclude(
            id=current_user.id
        ).select_related(
            'profile'
        ).prefetch_related(
            'profile__photos',
            'profile__interests'
        )
        
        # For now, just return users with profiles
        users = [u for u in users if hasattr(u, 'profile')]
        
        # Limit results
        users = users[:limit]
        
        # Serialize manually (simple version)
        results = []
        for user in users:
            profile = user.profile
            
            # Get primary photo or first photo
            primary_photo = profile.photos.filter(is_primary=True).first()
            if not primary_photo:
                primary_photo = profile.photos.first()
            
            photo_url = None
            if primary_photo:
                photo_url = request.build_absolute_uri(primary_photo.image.url)
            
            # Get interests
            interests = [
                pi.interest.name 
                for pi in profile.interests.all()[:5]
            ]
            
            results.append({
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
        
        return Response({
            'count': len(results),
            'results': results
        })
    
    @action(detail=False, methods=['post'])
    def swipe(self, request):
        """
        Record a swipe action (like or pass).
        
        POST /api/discovery/swipe/
        Body: {
            "target_user_uuid": "uuid",
            "action": "like" or "pass"
        }
        
        Returns whether it resulted in a mutual match.
        """
        target_uuid = request.data.get('target_user_uuid')
        action = request.data.get('action')
        
        # Validate input
        if not target_uuid or action not in ['like', 'pass']:
            return Response({
                'error': 'Invalid input. Provide target_user_uuid and action (like/pass)'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get target user
        try:
            target_user = User.objects.get(id=target_uuid)
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Create swipe action using service
        swipe, mutual_match = MatchingService.create_swipe_action(
            user=request.user,
            target_user=target_user,
            action=action
        )
        
        response_data = {
            'message': f'Successfully {action}d profile',
            'is_mutual_match': mutual_match is not None
        }
        
        if mutual_match:
            response_data['match'] = {
                'uuid': str(mutual_match.uuid),
                'matched_user': UserBriefSerializer(
                    target_user,
                    context={'request': request}
                ).data,
                'match_score': mutual_match.match_score
            }
        
        return Response(response_data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def profile_detail(self, request):
        """
        Get detailed profile for a potential match.
        
        GET /api/discovery/profile_detail/?uuid=xxx
        
        Records profile view for analytics.
        """
        profile_uuid = request.query_params.get('uuid')
        
        if not profile_uuid:
            return Response({
                'error': 'uuid parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.select_related('profile').prefetch_related(
                'profile__photos',
                'profile__interests'
            ).get(id=profile_uuid)
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Record profile view
        from .models import ProfileView
        ProfileView.objects.create(
            viewer=request.user,
            viewed_profile=user
        )
        
        # Increment profile view counter
        user.profile.increment_views()
        
        # Calculate match score
        match_score = MatchingService.calculate_match_score(request.user, user)
        
        # Serialize user data
        serializer = UserSerializer(user, context={'request': request})
        data = serializer.data
        data['match_score'] = match_score
        
        return Response(data, status=status.HTTP_200_OK)


class MatchViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing matches.
    """
    
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    lookup_field = 'uuid'

    def _get_base_queryset(self):
        """
        Returns the base, unsliced queryset for matches.
        """
        only_mutual = self.request.query_params.get('only_mutual', 'true').lower() == 'true'
        queryset = Match.objects.filter(
            user=self.request.user
        ).select_related(
            'matched_user__profile'
        ).prefetch_related(
            'matched_user__profile__photos',
            'matched_user__profile__interests'
        )
        if only_mutual:
            queryset = queryset.filter(is_mutual=True)
        return queryset

    def get_queryset(self):
        """
        Get user's matches, sliced for pagination.
        """
        return self._get_base_queryset().order_by('-created_at')[:100]

    def list(self, request, *args, **kwargs):
        """
        List all matches.
        
        GET /api/matches/
        
        Query params:
        - only_mutual: true/false (default: true)
        """
        queryset = self.get_queryset()
        paginator = self.pagination_class()
        paginated_matches = paginator.paginate_queryset(queryset, request)
        
        # Serialize matches with matched user data
        results = []
        for match in paginated_matches:
            results.append({
                'uuid': str(match.uuid),
                'matched_user': UserBriefSerializer(
                    match.matched_user,
                    context={'request': request}
                ).data,
                'match_score': match.match_score,
                'is_mutual': match.is_mutual,
                'matched_at': match.matched_at,
                'created_at': match.created_at
            })
        
        return paginator.get_paginated_response(results)
    
    @action(detail=False, methods=['get'])
    def count(self, request):
        """
        Get total match count.
        
        GET /api/matches/count/
        """
        base_queryset = self._get_base_queryset()
        total = base_queryset.count()
        mutual = base_queryset.filter(is_mutual=True).count()
        
        return Response({
            'total': total,
            'mutual': mutual
        }, status=status.HTTP_200_OK)
    
