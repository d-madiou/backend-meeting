from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.cache import cache
from datetime import date
import uuid

# ==============================
# Custom User Manager (Username + PIN Focus)
# ==============================
class UserManager(BaseUserManager):
    """
    Custom user manager that uses username instead of email.
    The 'password' passed here will be the user's 4-digit PIN.
    """
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError(_('Users must have a username'))

        # Normalize email only if it is provided
        if 'email' in extra_fields and extra_fields['email']:
            extra_fields['email'] = self.normalize_email(extra_fields['email'])

        user = self.model(username=username, **extra_fields)
        # Django securely hashes the 4-digit PIN here
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, password, **extra_fields)


# ==============================
# Custom User Model
# ==============================
class User(AbstractUser):
    """
    Extended User model tailored for Username + PIN authentication.
    Email is strictly optional.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True, db_index=True)

    # Email is now optional, used only for recovery or progressive profiling later
    email = models.EmailField(max_length=255, unique=True, null=True, blank=True)

    last_activity = models.DateTimeField(null=True, blank=True)

    # We can use this for Smile ID face verification status
    is_verified = models.BooleanField(
        default=False,
        help_text=_('Designates whether the user has passed face verification.')
    )

    objects = UserManager()

    # The magic switch: Make username the primary login identifier
    USERNAME_FIELD = 'username'
    # Remove email from required fields
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.username


# ==============================
# Profile Model (Marriage/Friendship Optimized)
# ==============================
class Profile(models.Model):
    """
    Extended profile information optimized for marriage and friendship.
    """

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    RELATIONSHIP_GOALS = [
        ('friendship', 'Friendship'),
        ('serious', 'Serious Relationship'),
        ('marriage', 'Marriage'),
    ]

    MARITAL_STATUS_CHOICES = [
        ('single', 'Single (Never Married)'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
        ('separated', 'Separated'),
    ]

    RELIGION_CHOICES = [
        ('muslim', 'Muslim'),
        ('christian', 'Christian'),
        ('hindu', 'Hindu'),
        ('buddhist', 'Buddhist'),
        ('traditional', 'Traditional'),
        ('other', 'Other'),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile', primary_key=True
    )

    # Basic Info
    bio = models.TextField(blank=True, help_text=_('Short biography or description'))
    birth_date = models.DateField(null=True, blank=True, help_text=_('Date of birth'))
    gender = models.CharField(max_length=2, choices=GENDER_CHOICES, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)

    # Marriage/Context Specifics
    relationship_goal = models.CharField(max_length=20, choices=RELATIONSHIP_GOALS, blank=True)
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, blank=True)
    religion = models.CharField(
        max_length=100,
        choices=RELIGION_CHOICES,
        blank=False,
        help_text=_('Select one religion option')
    )
    profession = models.CharField(max_length=150, blank=True, help_text=_('Job or profession'))
    education_level = models.CharField(max_length=100, blank=True)
    height_cm = models.PositiveIntegerField(null=True, blank=True, help_text=_('Height in centimeters'))

    looking_for_gender = models.CharField(
        max_length=2, choices=GENDER_CHOICES, blank=True, help_text=_('Gender you are looking for')
    )

    # Preferences
    min_age_preference = models.PositiveIntegerField(
        default=18, blank=True, validators=[MinValueValidator(18), MaxValueValidator(100)]
    )
    max_age_preference = models.PositiveIntegerField(
        default=60, blank=True, validators=[MinValueValidator(18), MaxValueValidator(100)]
    )
    max_distance_km = models.PositiveIntegerField(
        default=100, blank=True, help_text=_('Maximum distance in kilometers for matches')
    )

    # Statistics
    profile_completion_percentage = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    total_matches = models.PositiveIntegerField(default=0)
    profile_views = models.PositiveIntegerField(default=0)

    # Timestamp fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'profiles'
        indexes = [
            models.Index(fields=['gender', 'birth_date']),
            models.Index(fields=['city', 'country']),
            models.Index(fields=['relationship_goal']),
            models.Index(fields=['religion']),
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
            self.bio, self.birth_date, self.gender, self.city,
            self.relationship_goal, self.marital_status
        ]
        has_photos = hasattr(self, "photos") and self.photos.exists()
        return all(required_fields) and has_photos

    # ---------------------
    # Business Logic
    # ---------------------
    def calculate_completion_percentage(self):
        """
        Calculate how complete the profile is based on filled fields.
        """
        # Increased total fields to account for new marriage-focused attributes
        total_fields = 10
        filled_fields = 0

        if self.bio: filled_fields += 1
        if self.birth_date: filled_fields += 1
        if self.gender: filled_fields += 1
        if self.city: filled_fields += 1
        if self.relationship_goal: filled_fields += 1
        if self.marital_status: filled_fields += 1
        if self.profession: filled_fields += 1
        if self.religion: filled_fields += 1
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
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='profile_photos/')
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Photo for {self.profile.user.username}"

    def save(self, *args, **kwargs):
        if not ProfilePhoto.objects.filter(profile=self.profile).exists():
            self.is_primary = True
        super().save(*args, **kwargs)


# ==============================
# Interests
# ==============================
class Interest(models.Model):
    DEFAULT_INTEREST_NAMES = [
        'Cooking',
        'Travel',
        'Reading',
        'Sports',
        'Music',
        'Technology',
        'Movies',
        'Entrepreneurship',
        'Fitness',
        'Volunteering',
    ]

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
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='interests')
    interest = models.ForeignKey(Interest, on_delete=models.CASCADE, related_name='profiles')
    passion_level = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    class Meta:
        unique_together = ('profile', 'interest')
        db_table = 'profile_interests'

    def __str__(self):
        return f"{self.profile.user.username} → {self.interest.name}"
