from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.cache import cache
from datetime import date
import uuid


# ==============================
# Custom User Manager
# ==============================
class UserManager(BaseUserManager):
    """
    Custom user manager that uses email instead of username for authentication.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('Users must have an email address'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


# ==============================
# 👤 Custom User Model
# ==============================
class User(AbstractUser):
    """
    Extended User model with UUID and email-based authentication.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=255)
    username = models.CharField(max_length=150, unique=True)
    last_activity = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(
        default=False,
        help_text=_('Designates whether the user has verified their email address.')
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.username or self.email

    def get_full_name(self):
        """Return the user's full name with title case."""
        return super().get_full_name().title() if self.get_full_name() else self.username


# ==============================
# Profile Model
# ==============================
class Profile(models.Model):
    """
    Extended profile information for dating app users.
    Linked one-to-one with the User model.
    """

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]

    RELATIONSHIP_GOALS = [
        ('casual', 'Casual Dating'),
        ('serious', 'Serious Relationship'),
        ('friendship', 'Friendship'),
        ('marriage', 'Marriage'),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile', primary_key=True
    )
    bio = models.TextField(blank=True, help_text=_('Short biography or description'))
    birth_date = models.DateField(null=True, blank=True, help_text=_('Date of birth'))
    gender = models.CharField(max_length=2, choices=GENDER_CHOICES, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    relationship_goal = models.CharField(max_length=20, choices=RELATIONSHIP_GOALS, blank=True)
    looking_for_gender = models.CharField(
        max_length=2, choices=GENDER_CHOICES, blank=True, help_text=_('Gender you are looking for')
    )

    # Preferences
    min_age_preference = models.PositiveIntegerField(
        default=18, blank=True, validators=[MinValueValidator(18), MaxValueValidator(100)]
    )
    max_age_preference = models.PositiveIntegerField(
        default=100, blank=True, validators=[MinValueValidator(18), MaxValueValidator(100)]
    )
    max_distance_km = models.PositiveIntegerField(
        default=50, blank=True, help_text=_('Maximum distance in kilometers for matches')
    )

    # Statistics
    profile_completion_percentage = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    total_matches = models.PositiveIntegerField(default=0)
    total_messages_sent = models.PositiveIntegerField(default=0)
    profile_views = models.PositiveIntegerField(default=0)

    # Timestamp fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'profiles'
        indexes = [
            models.Index(fields=['gender', 'birth_date']),
            models.Index(fields=['city', 'country']),
            models.Index(fields=['profile_completion_percentage']),
        ]

    def __str__(self):
        return f"Profile of {self.user.username}"

    # ---------------------
    # Computed Properties
    # ---------------------
    @property
    def age(self):
        """Calculate age from birth_date and cache for performance."""
        if not self.birth_date:
            return None

        cache_key = f"profile_age_{self.user_id}"
        cached_age = cache.get(cache_key)
        if cached_age is not None:
            return cached_age

        today = date.today()
        age = today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )
        cache.set(cache_key, age, 86400) 
        return age

    @property
    def is_complete(self):
        """Check if profile has a minimum set of fields filled out."""
        required_fields = [
            self.bio, self.birth_date, self.gender, self.city, self.relationship_goal
        ]
        has_photos = hasattr(self, "photos") and self.photos.exists()
        return all(required_fields) and has_photos

    # ---------------------
    # Business Logic
    # ---------------------
    def calculate_completion_percentage(self):
        """
        Calculate how complete the profile is based on filled fields and media.
        """
        total_fields = 7
        filled_fields = 0

        if self.bio: filled_fields += 1
        if self.birth_date: filled_fields += 1
        if self.gender: filled_fields += 1
        if self.city: filled_fields += 1
        if self.country: filled_fields += 1
        if self.relationship_goal: filled_fields += 1
        if self.looking_for_gender: filled_fields += 1
        if hasattr(self, "photos") and self.photos.exists(): filled_fields += 1
        if hasattr(self, "interests") and self.interests.exists(): filled_fields += 1

        percentage = int((filled_fields / total_fields) * 100)
        self.profile_completion_percentage = percentage
        self.save(update_fields=['profile_completion_percentage'])
        return percentage

    def increment_views(self):
        """Safely increment profile view counter (atomic update)."""
        from django.db.models import F
        Profile.objects.filter(pk=self.pk).update(profile_views=F('profile_views') + 1)
        self.refresh_from_db()


# ==============================
# Profile Photo
# ==============================
class ProfilePhoto(models.Model):
    """
    Stores multiple photos for a profile.
    """
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='profile_photos/')
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Photo for {self.profile.user.username}"

    def save(self, *args, **kwargs):
        """Ensure the first uploaded photo is set as primary."""
        if not ProfilePhoto.objects.filter(profile=self.profile).exists():
            self.is_primary = True
        super().save(*args, **kwargs)


# ==============================
# Interests
# ==============================
class Interest(models.Model):
    """
    Represents an available interest/hobby (e.g. Music, Sports, Art).
    """
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        db_table = 'interests'

    def __str__(self):
        return self.name


# ==============================
# Profile Interests (Many-to-Many)
# ==============================
class ProfileInterest(models.Model):
    """
    Intermediate table connecting profiles to their interests.
    """
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='interests')
    interest = models.ForeignKey(Interest, on_delete=models.CASCADE, related_name='profiles')
    passion_level = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_('How passionate the user is about this interest (1–5)')
    )

    class Meta:
        unique_together = ('profile', 'interest')
        db_table = 'profile_interests'

    def __str__(self):
        return f"{self.profile.user.username} → {self.interest.name} ({self.passion_level})"
