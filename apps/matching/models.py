"""
Matching System Models
=======================
Demonstrates:
- Complex preference matching logic
- Score-based matching algorithm
- Efficient query optimization with indexes
- Caching strategies for match scores
"""

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
import uuid


# ============================================================================
# MATCH MODEL
# ============================================================================

class Match(models.Model):
    """
    Represents a match between two users.
    
    Design Pattern: Bidirectional match (if A matches B, B matches A).
    We store both directions for query efficiency.
    """
    
    MATCH_STATUS = [
        ('pending', 'Pending'),      # One user liked, waiting for response
        ('matched', 'Matched'),      # Both users liked each other
        ('passed', 'Passed'),        # User explicitly passed
        ('expired', 'Expired'),      # Match opportunity expired
    ]
    
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True
    )
    
    # User who initiated the like
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='matches_initiated'
    )
    
    # User who was liked
    matched_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='matches_received'
    )
    
    status = models.CharField(
        max_length=20,
        choices=MATCH_STATUS,
        default='pending',
        db_index=True
    )
    
    # Match score (0-100) based on compatibility algorithm
    match_score = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_('Compatibility score from 0-100'),
        db_index=True
    )
    
    # Track mutual interest
    is_mutual = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_('True if both users liked each other')
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    matched_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('When mutual match was made')
    )
    
    class Meta:
        db_table = 'matches'
        unique_together = ['user', 'matched_user']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'is_mutual']),
            models.Index(fields=['matched_user', 'status']),
            models.Index(fields=['-match_score', 'status']),
            models.Index(fields=['user', '-created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} -> {self.matched_user.username} ({self.status})"
    
    @classmethod
    def create_match(cls, user, matched_user, match_score):
        """
        Create a match between two users.
        """
        match, created = cls.objects.get_or_create(
            user=user,
            matched_user=matched_user,
            defaults={
                'match_score': match_score,
                'status': 'pending'
            }
        )
        return match, created

    def mark_as_mutual(self):
        """
        Mark this match as mutual match (both users liked each other).
        We will update the reverse match as well
        """
        from django.utils import timezone

        self.is_mutual = True
        self.status = 'matched'
        self.matched_at = timezone.now()
        self.save(update_fields=['is_mutual', 'status', 'matched_at'])

        #check if reverse match exist and update it
        try:
            reverse_match = Match.objects.get(
                user=self.matched_user,
                matched_user=self.user,
            )
            if not reverse_match.is_mutual:
                reverse_match.is_mutual = True
                reverse_match.status = 'matched'
                reverse_match.matched_at = timezone.now()
                reverse_match.save(update_fields=['is_mutual', 'status', 'matched_at'])
        except Match.DoesNotExist:
            #Then let's create a reverse match if it doesn't exist
            Match.objects.create(
                user=self.matched_user,
                matched_user=self.user,
                match_score=self.match_score,
                status='matched',
                is_mutual=True,
                matched_at=timezone.now()
            )

# ============================================================================
# USER PREFERENCE MODEL
# ============================================================================

class UserPreference(models.Model):
    """
    Detailed matching preferences beyond basic profile information.
    Allows users to fine-tune their matches.
    """
    IMPORTANCE_LEVELS=[
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Deal breaker')
    ]
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='matches_preferences',
        primary_key=True
    )

    #Deal breakers
    show_only_verified = models.BooleanField(
        default=False,
        help_text=_('Show only verified users'))
    hide_seen_profiles = models.PositiveIntegerField(default=True, help_text=_('Hide profile already viewed'))

    age_importance = models.PositiveIntegerField(
        choices=IMPORTANCE_LEVELS,
        default=2,
    )
    distance_importance = models.PositiveIntegerField(
        default=3,
        choices=IMPORTANCE_LEVELS
    )
    
    interests_importance = models.PositiveIntegerField(
        default=4,
        choices=IMPORTANCE_LEVELS,
        help_text=_('Weight for shared interests in matching')
    )
    
    relationship_goal_importance = models.PositiveIntegerField(
        default=5,
        choices=IMPORTANCE_LEVELS
    )
    
    # Advanced filters
    min_profile_completion = models.PositiveIntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_('Minimum profile completion percentage')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_preferences'
    
    def __str__(self):
        return f"Preferences for {self.user.username}"
    
# ============================================================================
# SWIPE ACTION MODEL
# ============================================================================

class SwipeAction(models.Model):
    """
    Records every swipe action (like/pass) for analytics and to prevent showing
    the same profile multiple times.
    
    Business Value:
    - Analytics: Track user behavior
    - User Experience: Don't show rejected profiles again
    - Match Making: Improve algorithm based on swipe patterns
    """
    
    ACTION_TYPES = [
        ('like', 'Like'),
        ('pass', 'Pass'),
    ]
    
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='swipe_actions'
    )
    
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_swipes'
    )
    
    action = models.CharField(
        max_length=20,
        choices=ACTION_TYPES,
        db_index=True
    )
    
    # Store match score at time of swipe for analytics
    match_score_at_swipe = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'swipe_actions'
        unique_together = ['user', 'target_user']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'action']),
            models.Index(fields=['target_user', 'action']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} {self.action} {self.target_user.username}"
    
    def save(self, *args, **kwargs):
        """
        Let's create match when the action is like 
        """
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and self.action == 'like':
            match, created = Match.create_match(
                user=self.user,
                matched_user=self.target_user,
                match_score=self.match_score_at_swipe
            )

            #Let's check if the target user is already like this user
            mutual_like_exists = SwipeAction.objects.filter(
                user=self.target_user,
                target_user=self.user,
                action='like'
            ).exists()

            if mutual_like_exists:
                match.mark_as_mutual()

# ============================================================================
# PROFILE VIEW MODEL
# ============================================================================

class ProfileView(models.Model):
    """
    Tracks when users view other profiles.
    Used for:
    - Analytics
    - Showing "who viewed me" feature
    - Not showing same profiles repeatedly
    """
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='viewed_profiles'
    )
    
    viewed_profile = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile_views_received'
    )

    #Let's track how long they viewed the profile
    view_duration_seconds = models.PositiveIntegerField(
        default=0,
        help_text=_('Duration of the view in seconds')
    )
    #Track if user swiped after viewing
    resulted_in_swipe = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'profile_views'
        indexes = [
            models.Index(fields=['viewer', '-created_at']),
            models.Index(fields=['viewed_profile', '-created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.viewer.username} viewed {self.viewed_profile.username}"
    
# ============================================================================
# BLOCK MODEL
# ============================================================================

class Block(models.Model):
    """
    Users can block others to prevent them from appearing in discovery
    or contacting them.
    
    Business Rule: Blocking is one-way and immediate.
    """
    BLOCK_REASONS = [
        ('inappropriate', 'Inappropriate Behavior'),
        ('harassment', 'Harassment'),
        ('spam', 'Spam'),
        ('fake', 'Fake Profile'),
        ('other', 'Other'),
    ]
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blocks_made'
    )
    blocked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blocks_received'
    )
    reason = models.CharField(
        max_length=20,
        choices=BLOCK_REASONS,
        default='other',
        blank=True
    )
    note = models.TextField(blank=True, help_text=_('Optional note for the block'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'blocks'
        unique_together = ['blocker', 'blocked_user']
        indexes = [
            models.Index(fields=['blocker', '-created_at']),
            models.Index(fields=['blocked_user', '-created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked_user.username}"
    
    @classmethod
    def is_blocked(cls, user1, user2):
        """
        Check if two users are blocked each other.
        cached for better performance
        """
        cache_key = f'block_check_{min(user1.id, user2.id)}_{max(user1.id, user2.id)}'
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        is_blocked = cls.objects.filter(
            models.Q(blocker=user1, blocked_user=user2) |
            models.Q(blocker=user2, blocked_user=user1)
        ).exists()
        cache.set(cache_key, is_blocked, 300)
        return is_blocked
        