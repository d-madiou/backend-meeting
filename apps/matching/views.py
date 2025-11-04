from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from apps.users.models import User, Profile

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