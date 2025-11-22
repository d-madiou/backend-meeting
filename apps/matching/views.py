from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from apps.common.pagination import StandardResultsSetPagination
from apps.matching.services import MatchingService
from .models import Match, SwipeAction
from apps.users.models import User, Profile
from apps.users.serializers import UserBriefSerializer, UserSerializer
from apps.users.utils.push_notifications import send_like_notification, send_match_notification

from apps.users.utils.push_notifications import send_like_notification, send_match_notification 
from django.utils import timezone

# ============================================================================
# FEED VIEWSET
# ============================================================================
class FeedViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        Get feed of potential matches.
        """
        limit = int(request.query_params.get('limit', 20))
        current_user = request.user

        users = User.objects.filter(is_active=True)\
            .exclude(id=current_user.id)\
            .select_related('profile')\
            .prefetch_related('profile__photos', 'profile__interests')

        users = [u for u in users if hasattr(u, 'profile')]
        users = users[:limit]

        results = []
        for user in users:
            profile = user.profile
            primary_photo = profile.photos.filter(is_primary=True).first() or profile.photos.first()
            photo_url = request.build_absolute_uri(primary_photo.image.url) if primary_photo else None
            interests = [pi.interest.name for pi in profile.interests.all()[:5]]
            
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

        return Response({'count': len(results), 'results': results})
    
    @action(detail=False, methods=['post'])
    def swipe(self, request):
        """
        Record a swipe action (like or pass) and send notifications.
        """
        target_uuid = request.data.get('target_user_uuid')
        action = request.data.get('action')

        # --- Input validation ---
        if not target_uuid or action not in ['like', 'pass']:
            return Response({
                'error': 'Invalid input. Provide target_user_uuid and action (like/pass).'
            }, status=status.HTTP_400_BAD_REQUEST)

        # --- Check if target user exists ---
        try:
            target_user = User.objects.get(id=target_uuid)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        # --- Create the swipe action (delegated to service) ---
        swipe, mutual_match = MatchingService.create_swipe_action(
            user=request.user,
            target_user=target_user,
            action=action
        )

        # --- Handle notification logic for 'like' ---
        if action == 'like':
            # Notify target user someone liked them
            send_like_notification(
                liker_username=request.user.username,
                liked_user_id=str(target_user.id),
                liker_user_id=str(request.user.id)
            )

            # If it's a mutual match
            if mutual_match:
                mutual_match.mark_as_mutual()

                # Send match notifications to both users
                send_match_notification(
                    matched_username=target_user.username,
                    user_id=str(request.user.id),
                    match_id=str(mutual_match.id),
                    matched_user_id=str(target_user.id)
                )
                send_match_notification(
                    matched_username=request.user.username,
                    user_id=str(target_user.id),
                    match_id=str(mutual_match.id),
                    matched_user_id=str(request.user.id)
                )

        # --- Prepare response ---
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
        """
        profile_uuid = request.query_params.get('uuid')
        if not profile_uuid:
            return Response({'error': 'uuid parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.select_related('profile').prefetch_related(
                'profile__photos', 'profile__interests'
            ).get(id=profile_uuid)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        
        from .models import ProfileView
        ProfileView.objects.create(viewer=request.user, viewed_profile=user)
        user.profile.increment_views()
        
        match_score = MatchingService.calculate_match_score(request.user, user)
        serializer = UserSerializer(user, context={'request': request})
        data = serializer.data
        data['match_score'] = match_score
        
        return Response(data, status=status.HTTP_200_OK)
    


# ============================================================================
# MATCH VIEWSET (merged)
# ============================================================================
class MatchViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def list(self, request):
        """
        Return categorized matches:
        - sent_likes
        - received_likes
        - mutual_matches
        """
        current_user = request.user

        # --- SENT LIKES ---
        sent_likes = Match.objects.filter(user=current_user)\
            .select_related('matched_user__profile')\
            .prefetch_related('matched_user__profile__photos')

        sent_likes_data = []
        for match in sent_likes:
            primary_photo = match.matched_user.profile.photos.filter(is_primary=True).first() or \
                match.matched_user.profile.photos.first() if hasattr(match.matched_user, 'profile') and match.matched_user.profile else None
            photo_url = request.build_absolute_uri(primary_photo.image.url) if primary_photo and hasattr(primary_photo, 'image') else None

            status_value = 'matched' if match.is_mutual else (
                'rejected' if SwipeAction.objects.filter(
                    user=match.matched_user, target_user=current_user, action='pass'
                ).exists() else 'pending'
            )

            sent_likes_data.append({
                'id': str(match.id),
                'liked_user': {
                    'id': str(match.matched_user.id),
                    'username': match.matched_user.username,
                    'age': match.matched_user.profile.age if hasattr(match.matched_user, 'profile') else None,
                    'city': match.matched_user.profile.city if hasattr(match.matched_user, 'profile') else None,
                    'photo_url': photo_url,
                },
                'status': status_value,
                'created_at': match.created_at.isoformat(),
            })


        # --- RECEIVED LIKES ---
        received_likes = Match.objects.filter(matched_user=current_user, is_mutual=False)\
            .select_related('user__profile')\
            .prefetch_related('user__profile__photos')


        received_likes_data = []
        for match in received_likes:
            you_passed = SwipeAction.objects.filter(
                user=current_user, target_user=match.user, action='pass'
            ).exists()

            if not you_passed:
                primary_photo = match.user.profile.photos.filter(is_primary=True).first() or \
                    match.user.profile.photos.first() if hasattr(match.user, 'profile') and match.user.profile else None
                photo_url = request.build_absolute_uri(primary_photo.image.url) if primary_photo and hasattr(primary_photo, 'image') else None

                received_likes_data.append({
                    'id': str(match.id),
                    'liker_user': {
                        'id': str(match.user.id),
                        'username': match.user.username,
                        'age': match.user.profile.age if hasattr(match.user, 'profile') else None,
                        'city': match.user.profile.city if hasattr(match.user, 'profile') else None,
                        'photo_url': photo_url,
                    },

                    'match_score': match.match_score,
                    'created_at': match.created_at.isoformat(),
                })

        # --- MUTUAL MATCHES ---
        mutual_matches = Match.objects.filter(user=current_user, is_mutual=True)\
            .select_related('matched_user__profile')\
            .prefetch_related('matched_user__profile__photos')


        mutual_matches_data = []
        for match in mutual_matches:
            primary_photo = match.matched_user.profile.photos.filter(is_primary=True).first() or \
                match.matched_user.profile.photos.first() if hasattr(match.matched_user, 'profile') and match.matched_user.profile else None
            photo_url = request.build_absolute_uri(primary_photo.image.url) if primary_photo and hasattr(primary_photo, 'image') else None

            mutual_matches_data.append({
                'id': str(match.id),
                'matched_user': {
                    'id': str(match.matched_user.id),
                    'username': match.matched_user.username,
                    'age': match.matched_user.profile.age if hasattr(match.matched_user, 'profile') else None,
                    'city': match.matched_user.profile.city if hasattr(match.matched_user, 'profile') else None,
                    'country': match.matched_user.profile.country,
                    'photo_url': photo_url,
                },
                'match_score': match.match_score,
                'is_mutual': True,
                'status': 'matched',
                'matched_at': match.matched_at.isoformat() if match.matched_at else None,
                'created_at': match.created_at.isoformat(),
            })

        return Response({
            'sent_likes': sent_likes_data,
            'received_likes': received_likes_data,
            'mutual_matches': mutual_matches_data,
        })

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """
        Accept a received like → create mutual match.
        """
        try:
            match = Match.objects.get(id=pk, matched_user=request.user)
            initiator_user = match.user  # The user who originally liked the current user

            # from django.utils import timezone # Already imported above for clarity
            
            # 1. Create swipe action for the acceptor (current user)
            SwipeAction.objects.get_or_create(
                user=request.user,
                target_user=initiator_user,
                defaults={'action': 'like', 'match_score_at_swipe': match.match_score}
            )
            
            # 2. Update the existing Match object (User -> Current User)
            match.is_mutual = True
            match.status = 'matched'
            match.matched_at = timezone.now()
            match.save()

            # 3. Create/Update the reverse Match object (Current User -> User)
            reverse_match, _ = Match.objects.get_or_create(
                user=request.user,
                matched_user=initiator_user,
                defaults={
                    'match_score': match.match_score,
                    'is_mutual': True,
                    'status': 'matched',
                    'matched_at': timezone.now()
                }
            )
            reverse_match.is_mutual = True
            reverse_match.status = 'matched'
            reverse_match.matched_at = timezone.now()
            reverse_match.save()

            # 4. PUSH NOTIFICATION LOGIC
            
            # Notify the initiator user (the one who originally liked first)
            send_match_notification(
                matched_username=request.user.username,
                user_id=str(initiator_user.id),
                match_id=str(match.id),
                matched_user_id=str(request.user.id)  # 🎯 FIX: Pass the current user's ID
            )
            
            # Notify the current user (the one who accepted)
            send_match_notification(
                matched_username=initiator_user.username,
                user_id=str(request.user.id),
                match_id=str(match.id),
                matched_user_id=str(initiator_user.id) # 🎯 FIX: Pass the initiator's ID
            )
            
            # 5. Prepare response
            photo_url = None
            if hasattr(initiator_user, 'profile') and initiator_user.profile:
                primary_photo = initiator_user.profile.photos.filter(is_primary=True).first() or \
                                initiator_user.profile.photos.first()
                if primary_photo and hasattr(primary_photo, 'image'):
                    photo_url = request.build_absolute_uri(primary_photo.image.url)

            return Response({
                'message': 'Match accepted successfully!',
                'is_mutual_match': True,
                'match': {
                    'id': str(match.id),
                    'matched_user': {
                        'id': str(initiator_user.id),
                        'username': initiator_user.username,
                        'age': initiator_user.profile.age if hasattr(initiator_user, 'profile') else None,
                        'city': initiator_user.profile.city if hasattr(initiator_user, 'profile') else None,
                        'photo_url': photo_url,
                    },
                    'match_score': match.match_score,
                    'matched_at': match.matched_at.isoformat(),
                }
            })

        except Match.DoesNotExist:
            return Response({'error': 'Match not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Reject a received like.
        """
        try:
            match = Match.objects.get(id=pk, matched_user=request.user)
            SwipeAction.objects.get_or_create(
                user=request.user,
                target_user=match.user,
                defaults={'action': 'pass', 'match_score_at_swipe': match.match_score}
            )
            match.status = 'rejected'
            match.save()
            return Response({'message': 'Like rejected successfully'})
        except Match.DoesNotExist:
            return Response({'error': 'Match not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def count(self, request):
        """
        Return match counts: total, mutual, pending.
        """
        current_user = request.user

        total = Match.objects.filter(
            Q(user=current_user) | Q(matched_user=current_user)
        ).count()

        mutual = Match.objects.filter(user=current_user, is_mutual=True).count()

        pending = Match.objects.filter(matched_user=current_user, is_mutual=False)\
            .exclude(
                user__in=SwipeAction.objects.filter(
                    user=current_user, action='pass'
                ).values_list('target_user', flat=True)
            ).count()

        return Response({'total': total, 'mutual': mutual, 'pending': pending})
    
    @action(detail=False, methods=['post'], url_path='block')
    def block_user(self, request):
        """
        Block a user.
        
        POST /api/matching/block/
        Body: {
            "blocked_user_id": "user_uuid",
            "reason": "spam" (optional)
        }
        """
        blocked_user_id = request.data.get('blocked_user_id')
        reason = request.data.get('reason', '')
        
        if not blocked_user_id:
            return Response({
                'error': 'blocked_user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from apps.users.models import User
            from apps.matching.models import Block
            
            blocked_user = User.objects.get(id=blocked_user_id)
            
            # Create block
            block, created = Block.objects.get_or_create(
                blocker=request.user,
                blocked_user=blocked_user,
                defaults={'reason': reason}
            )
            
            # Delete any existing matches
            from apps.matching.models import Match
            Match.objects.filter(
                Q(user=request.user, matched_user=blocked_user) |
                Q(user=blocked_user, matched_user=request.user)
            ).delete()
            
            return Response({
                'message': 'User blocked successfully',
                'created': created
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)