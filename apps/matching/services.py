"""
Matching Service Layer
=======================
Demonstrates:
- Complex matching algorithm with multiple factors
- Efficient QuerySet optimization with select_related/prefetch_related
- Caching strategies for expensive computations
- Score-based ranking system

The matching algorithm considers:
1. Age compatibility (within user's preferred age range)
2. Distance (within user's max distance)
3. Shared interests (weighted by importance)
4. Relationship goals alignment
5. Gender preferences
"""

from django.db.models import Q, F, Count, Prefetch, Case, When, IntegerField
from django.core.cache import cache
from django.conf import settings
from datetime import date, datetime
import math
import logging

from .models import (
    Match, SwipeAction, ProfileView, 
    Block, UserPreference
)
from apps.users.models import User, Profile

logger = logging.getLogger(__name__)


# ============================================================================
# MATCHING SERVICE
# ============================================================================

class MatchingService:
    """
    Core matching algorithm and discovery logic.
    
    Design Philosophy:
    - Score-based matching (0-100)
    - Configurable weights based on user preferences
    - Efficient queries using database-level filtering
    - Caching for expensive calculations
    """
    
    @staticmethod
    def calculate_age_score(user_age, target_age, min_age, max_age, importance=3):
        """
        Calculate compatibility score based on age.
        
        Args:
            user_age: The user's age
            target_age: The potential match's age
            min_age: User's minimum age preference
            max_age: User's maximum age preference
            importance: How important age is (1-5)
        
        Returns:
            int: Score from 0-100
        """
        # If target is outside preference range, return 0
        if target_age < min_age or target_age > max_age:
            return 0
        
        # Calculate how close target is to ideal age (middle of range)
        ideal_age = (min_age + max_age) / 2
        age_diff = abs(target_age - ideal_age)
        range_size = max_age - min_age
        
        if range_size == 0:
            # If range is a single age, perfect match if equal
            return 100 if age_diff == 0 else 0
        
        # Score decreases linearly as we move away from ideal age
        raw_score = 100 - (age_diff / range_size * 100)
        
        # Apply importance weight
        weighted_score = raw_score * (importance / 5)
        
        return max(0, min(100, int(weighted_score)))
    
    # @staticmethod
    # def calculate_distance_score(user_lat, user_lon, target_lat, target_lon, 
    #                              max_distance_km, importance=3):
    #     """
    #     Calculate compatibility score based on distance.
        
    #     Uses Haversine formula for distance calculation.
        
    #     Args:
    #         user_lat: User's latitude
    #         user_lon: User's longitude
    #         target_lat: Target's latitude
    #         target_lon: Target's longitude
    #         max_distance_km: Maximum acceptable distance
    #         importance: How important distance is (1-5)
        
    #     Returns:
    #         int: Score from 0-100
    #     """
    #     if not all([user_lat, user_lon, target_lat, target_lon]):
    #         # If location data is missing, return neutral score
    #         return 50
        
    #     # Calculate distance using Haversine formula
    #     distance_km = MatchingService._calculate_distance(
    #         float(user_lat), float(user_lon),
    #         float(target_lat), float(target_lon)
    #     )
        
    #     # If beyond max distance, return 0
    #     if distance_km > max_distance_km:
    #         return 0
        
    #     # Score decreases as distance increases
    #     raw_score = 100 - (distance_km / max_distance_km * 100)
        
    #     # Apply importance weight
    #     weighted_score = raw_score * (importance / 5)
        
    #     return max(0, min(100, int(weighted_score)))
    
    # @staticmethod
    # def _calculate_distance(lat1, lon1, lat2, lon2):
    #     """
    #     Calculate distance between two coordinates using Haversine formula.
        
    #     Returns distance in kilometers.
    #     """
    #     # Radius of Earth in kilometers
    #     R = 6371.0
        
    #     # Convert to radians
    #     lat1_rad = math.radians(lat1)
    #     lon1_rad = math.radians(lon1)
    #     lat2_rad = math.radians(lat2)
    #     lon2_rad = math.radians(lon2)
        
    #     # Differences
    #     dlat = lat2_rad - lat1_rad
    #     dlon = lon2_rad - lon1_rad
        
    #     # Haversine formula
    #     a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    #     c = 2 * math.asin(math.sqrt(a))
        
    #     distance = R * c
    #     return distance
    
    @staticmethod
    def calculate_interest_score(user_interests, target_interests, importance=4):
        """
        Calculate compatibility score based on shared interests.
        
        Args:
            user_interests: QuerySet or list of user's interests
            target_interests: QuerySet or list of target's interests
            importance: How important interests are (1-5)
        
        Returns:
            int: Score from 0-100
        """
        if not user_interests or not target_interests:
            return 50  # Neutral score if data missing
        
        # Convert to sets of interest IDs for efficient comparison
        user_interest_ids = set(
            i.id if hasattr(i, 'id') else i 
            for i in user_interests
        )
        target_interest_ids = set(
            i.id if hasattr(i, 'id') else i 
            for i in target_interests
        )
        
        # Calculate Jaccard similarity (intersection over union)
        if not user_interest_ids and not target_interest_ids:
            return 50
        
        intersection = len(user_interest_ids & target_interest_ids)
        union = len(user_interest_ids | target_interest_ids)
        
        if union == 0:
            return 50
        
        # Jaccard similarity as percentage
        raw_score = (intersection / union) * 100
        
        # Apply importance weight
        weighted_score = raw_score * (importance / 5)
        
        return max(0, min(100, int(weighted_score)))
    
    @staticmethod
    def calculate_relationship_goal_score(user_goal, target_goal, importance=5):
        """
        Calculate compatibility score based on relationship goals.
        
        Args:
            user_goal: User's relationship goal
            target_goal: Target's relationship goal
            importance: How important this is (1-5)
        
        Returns:
            int: Score from 0-100
        """
        if not user_goal or not target_goal:
            return 50  # Neutral if missing
        
        # Exact match is best
        if user_goal == target_goal:
            raw_score = 100
        # 'unsure' is compatible with anything
        elif user_goal == 'unsure' or target_goal == 'unsure':
            raw_score = 75
        # Serious and casual are incompatible
        elif (user_goal == 'serious' and target_goal == 'casual') or \
             (user_goal == 'casual' and target_goal == 'serious'):
            raw_score = 20
        else:
            raw_score = 50
        
        # Apply importance weight
        weighted_score = raw_score * (importance / 5)
        
        return max(0, min(100, int(weighted_score)))
    
    @staticmethod
    def calculate_match_score(user, target_user):
        """
        Calculate overall match score between two users.
        
        This is the core matching algorithm that combines all factors.
        
        Args:
            user: User object (with profile)
            target_user: Potential match User object (with profile)
        
        Returns:
            int: Overall match score from 0-100
        """
        # Get user preferences (use defaults if not set)
        try:
            preferences = user.matches_preferences
        except UserPreference.DoesNotExist:
            # Create default preferences
            preferences = UserPreference.objects.create(user=user)
        
        user_profile = user.profile
        target_profile = target_user.profile
        
        # Component scores
        scores = {}
        weights = {}
        
        # 1. Age compatibility
        if target_profile.age:
            scores['age'] = MatchingService.calculate_age_score(
                user_age=user_profile.age or 25,  # Default if missing
                target_age=target_profile.age,
                min_age=user_profile.min_age_preference,
                max_age=user_profile.max_age_preference,
                importance=preferences.age_importance
            )
            weights['age'] = preferences.age_importance
        
        # 3. Shared interests
        user_interests = user_profile.interests.all()
        target_interests = target_profile.interests.all()
        scores['interests'] = MatchingService.calculate_interest_score(
            user_interests=user_interests,
            target_interests=target_interests,
            importance=preferences.interests_importance
        )
        weights['interests'] = preferences.interests_importance
        
        # 4. Relationship goals
        scores['goals'] = MatchingService.calculate_relationship_goal_score(
            user_goal=user_profile.relationship_goal,
            target_goal=target_profile.relationship_goal,
            importance=preferences.relationship_goal_importance
        )
        weights['goals'] = preferences.relationship_goal_importance
        
        # Calculate weighted average
        if not scores:
            return 50  # Default score if no data
        
        total_weighted_score = sum(
            scores[key] * weights.get(key, 3) 
            for key in scores
        )
        total_weight = sum(weights.get(key, 3) for key in scores)
        
        if total_weight == 0:
            return 50
        
        final_score = int(total_weighted_score / total_weight)
        
        return max(0, min(100, final_score))
    
    @staticmethod
    def get_potential_matches(user, limit=20):
        """
        Get potential matches for a user using optimized queries.
        
        This is the main discovery feed query.
        
        Demonstrates:
        - Complex QuerySet with multiple filters
        - select_related and prefetch_related for optimization
        - Excluding already seen profiles
        - Filtering by preferences
        
        Args:
            user: User object
            limit: Maximum number of matches to return
        
        Returns:
            QuerySet: User objects ordered by match score
        """
        # Check cache first
        cache_key = f'potential_matches_{user.id}_limit_{limit}'
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        user_profile = user.profile
        
        # Get user preferences
        try:
            preferences = user.matches_preferences
        except UserPreference.DoesNotExist:
            preferences = UserPreference.objects.create(user=user)
        
        # Build base query
        potential_matches = User.objects.filter(
            is_active=True
        ).exclude(
            id=user.id  # Don't show self
        ).select_related(
            'profile'
        ).prefetch_related(
            'profile__interests',
            'profile__photos'
        )
        
        # Filter by gender preference
        if user_profile.looking_for_gender:
            potential_matches = potential_matches.filter(
                profile__gender=user_profile.looking_for_gender
            )
        
        # Filter by age range
        if user_profile.age:
            # Calculate birth year range
            current_year = date.today().year
            max_birth_year = current_year - user_profile.min_age_preference
            min_birth_year = current_year - user_profile.max_age_preference - 1
            
            potential_matches = potential_matches.filter(
                profile__birth_date__year__gte=min_birth_year,
                profile__birth_date__year__lte=max_birth_year
            )
        
        # Filter by minimum profile completion
        potential_matches = potential_matches.filter(
            profile__profile_completion_percentage__gte=preferences.min_profile_completion
        )
        
        # Exclude users who have blocked or been blocked by this user
        blocked_users = Block.objects.filter(
            Q(blocker=user) | Q(blocked_user=user)
        ).values_list('blocked_user_id', 'blocker_id')
        
        blocked_ids = set()
        for blocked_id, blocker_id in blocked_users:
            blocked_ids.add(blocked_id)
            blocked_ids.add(blocker_id)
        
        if blocked_ids:
            potential_matches = potential_matches.exclude(id__in=blocked_ids)
        
        # Exclude users already swiped on (if preference set)
        if preferences.hide_seen_profiles:
            already_swiped = SwipeAction.objects.filter(
                user=user
            ).values_list('target_user_id', flat=True)
            
            potential_matches = potential_matches.exclude(id__in=already_swiped)
        
        # Limit query
        potential_matches = potential_matches[:limit * 3]  # Get extra for scoring
        
        # Calculate match scores for each potential match
        scored_matches = []
        for potential_match in potential_matches:
            try:
                score = MatchingService.calculate_match_score(user, potential_match)
                
                # Only include if score meets minimum threshold
                if score >= settings.MIN_MATCH_SCORE:
                    scored_matches.append((potential_match, score))
            except Exception as e:
                logger.error(f"Error calculating match score: {e}")
                continue
        
        # Sort by score (highest first)
        scored_matches.sort(key=lambda x: x[1], reverse=True)
        
        # Get top matches
        result = [match[0] for match in scored_matches[:limit]]
        
        # Cache for 5 minutes
        cache.set(cache_key, result, 300)
        
        return result
    
    @staticmethod
    def create_swipe_action(user, target_user, action):
        """
        Record a swipe action (like/pass).
        
        Args:
            user: User performing the swipe
            target_user: User being swiped on
            action: 'like' or 'pass'
        
        Returns:
            tuple: (SwipeAction, Match or None if not mutual)
        """
        # Calculate match score at time of swipe
        match_score = MatchingService.calculate_match_score(user, target_user)

        # Use update_or_create to handle existing swipes
        swipe, created = SwipeAction.objects.update_or_create(
            user=user,
            target_user=target_user,
            defaults={
                'action': action,
                'match_score_at_swipe': match_score
            }
        )

        # Invalidate cache
        cache_key = f'potential_matches_{user.id}_limit_20'
        cache.delete(cache_key)

        mutual_match = None
        if action == 'like':
            # Create a match record for the person who just liked
            match, _ = Match.create_match(
                user=user,
                matched_user=target_user,
                match_score=match_score
            )

            # Check if the other person has already liked back
            if SwipeAction.objects.filter(user=target_user, target_user=user, action='like').exists():
                # It's a mutual match!
                mutual_match = match
                mutual_match.mark_as_mutual()
                logger.info(
                    f"Mutual match created: {user.username} <-> {target_user.username}"
                )

        return swipe, mutual_match
    
    @staticmethod
    def get_user_matches(user, only_mutual=True, limit=50):
        """
        Get user's matches.
        
        Args:
            user: User object
            only_mutual: If True, only return mutual matches
            limit: Maximum number to return
        
        Returns:
            QuerySet: Match objects with related user data
        """
        matches = Match.objects.filter(
            user=user
        ).select_related(
            'matched_user__profile'
        ).prefetch_related(
            'matched_user__profile__photos',
            'matched_user__profile__interests'
        )
        
        if only_mutual:
            matches = matches.filter(is_mutual=True)
        
        return matches.order_by('-created_at')[:limit]