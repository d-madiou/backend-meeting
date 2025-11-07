"""
User & Profile Serializers
===========================
Demonstrates:
- Separation of read/write serializers for security
- Nested serializers for complex relationships
- Custom validation methods
- Field-level permissions
- Write-only vs read-only fields
"""

from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from datetime import date

from .models import User, Profile, ProfilePhoto, Interest, ProfileInterest


# ============================================================================
# AUTHENTICATION SERIALIZERS
# ============================================================================

class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for minimal user registration.
    Design: Only collect essential information at registration.
    Profile details collected in separate step after authentication.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm']
        extra_kwargs = {'email': {'required': True}}

    def validate(self, attrs):
        """
        Validate that passwords match.
        """
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Passwords do not match.'
            })
        return attrs

    def create(self, validated_data):
        """
        Create user with hashed password.
        """
        validated_data.pop('password_confirm')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        Profile.objects.create(user=user)
        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login.
    Returns user data and authentication token.
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )

    def validate(self, attrs):
        """
        Validate credentials and authenticate user.
        """
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(
                request=self.context.get('request'),
                email=email,
                password=password
            )
            if not user:
                raise serializers.ValidationError(
                    'Unable to login with provided credentials.',
                    code='authorization'
                )
            if not user.is_active:
                raise serializers.ValidationError(
                    'User account is disabled.',
                    code='authorization'
                )
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError(
                'Must include "email" and "password".',
                code='authorization'
            )


# ============================================================================
# PROFILE SERIALIZERS
# ============================================================================

class ProfilePhotoSerializer(serializers.ModelSerializer):
    """
    Serializer for profile photos.
    """
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProfilePhoto
        fields = ['id', 'url', 'is_primary', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

    def get_url(self, obj):
        """
        Return full URL for the image.
        """
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class InterestSerializer(serializers.ModelSerializer):
    """
    Serializer for interests.
    """
    class Meta:
        model = Interest
        fields = ['id', 'name']
        read_only_fields = ['id']


class ProfileInterestSerializer(serializers.ModelSerializer):
    """
    Serializer for profile interests with passion level.
    """
    interest = InterestSerializer(read_only=True)
    interest_id = serializers.PrimaryKeyRelatedField(
        queryset=Interest.objects.all(),
        source='interest',
        write_only=True
    )

    class Meta:
        model = ProfileInterest
        fields = ['interest', 'interest_id', 'passion_level']
        read_only_fields = []


class ProfileSerializer(serializers.ModelSerializer):
    """
    Read serializer for Profile model.
    Includes all profile information for display.
    """
    age = serializers.IntegerField(read_only=True)
    photos = ProfilePhotoSerializer(many=True, read_only=True)
    interests = ProfileInterestSerializer(many=True, read_only=True)
    is_complete = serializers.BooleanField(read_only=True)

    class Meta:
        model = Profile
        fields = [
            'bio', 'birth_date', 'age', 'gender',
            'city', 'country',
            'relationship_goal', 'looking_for_gender',
            'min_age_preference', 'max_age_preference', 'max_distance_km',
            'profile_completion_percentage', 'is_complete',
            'total_matches', 'total_messages_sent', 'profile_views',
            'photos', 'interests',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'profile_completion_percentage', 'total_matches',
            'total_messages_sent', 'profile_views',
            'created_at', 'updated_at'
        ]


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Write serializer for updating profile.
    Design Pattern: Separate write serializer for updates.
    """
    class Meta:
        model = Profile
        fields = [
            'bio', 'birth_date', 'gender',
            'city', 'country',
            'relationship_goal', 'looking_for_gender',
            'min_age_preference', 'max_age_preference', 'max_distance_km'
        ]

    def validate_birth_date(self, value):
        """
        Ensure user is at least 18 years old.
        """
        if value:
            today = date.today()
            age = today.year - value.year - (
                (today.month, today.day) < (value.month, value.day)
            )
            if age < 18:
                raise serializers.ValidationError(
                    'You must be at least 18 years old to use this app.'
                )
        return value

    def validate(self, attrs):
        """
        Validate age preferences.
        """
        min_age = attrs.get('min_age_preference')
        max_age = attrs.get('max_age_preference')
        if min_age and max_age and min_age > max_age:
            raise serializers.ValidationError({
                'min_age_preference': 'Minimum age cannot be greater than maximum age.'
            })
        return attrs

    def update(self, instance, validated_data):
        """
        Update profile and recalculate completion percentage.
        """
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        instance.calculate_completion_percentage()
        return instance


class UserSerializer(serializers.ModelSerializer):
    """
    Read serializer for User model including profile data.
    """
    profile = ProfileSerializer(read_only=True)
    is_profile_complete = serializers.BooleanField(source='profile.is_complete', read_only=True)
    created_at = serializers.DateTimeField(source='profile.created_at', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'is_verified',
            'is_profile_complete', 'last_activity', 'created_at', 'profile' # 'created_at' is now sourced from profile
        ]
        read_only_fields = [
            'id', 'is_verified', 'is_profile_complete', 'last_activity', 'created_at' # 'created_at' is now sourced from profile
        ]


class UserBriefSerializer(serializers.ModelSerializer):
    """
    Lightweight user serializer for lists.
    """
    primary_photo = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'primary_photo', 'age', 'city']

    def get_primary_photo(self, obj):
        """
        Get URL of primary photo.
        """
        request = self.context.get('request')
        primary_photo = obj.profile.photos.filter(is_primary=True).first()
        if primary_photo and request:
            return request.build_absolute_uri(primary_photo.image.url)
        return None

    def get_age(self, obj):
        """
        Get user's age from profile.
        """
        return getattr(obj.profile, 'age', None)

    def get_city(self, obj):
        """
        Get user's city from profile.
        """
        return getattr(obj.profile, 'city', None)


class ProfilePhotoUploadSerializer(serializers.ModelSerializer):
    """
    Serializer for uploading profile photos.
    """
    class Meta:
        model = ProfilePhoto
        fields = ['image', 'is_primary']

    def validate(self, attrs):
        """
        Validate photo upload.
        """
        from django.conf import settings
        profile = self.context['profile']
        current_photo_count = profile.photos.count()
        max_photos = getattr(settings, 'MAX_PROFILE_PHOTOS', 6)
        if current_photo_count >= max_photos:
            raise serializers.ValidationError(
                f'You can only upload up to {max_photos} photos.'
            )
        return attrs

    def create(self, validated_data):
        """
        Create photo associated with user's profile.
        """
        profile = self.context['profile']
        photo = ProfilePhoto.objects.create(profile=profile, **validated_data)
        profile.calculate_completion_percentage()
        return photo


# ============================================================================
# RESPONSE SERIALIZERS (for consistent API responses)
# ============================================================================

class AuthResponseSerializer(serializers.Serializer):
    """
    Serializer for authentication responses.
    """
    user = UserSerializer(read_only=True)
    token = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)


class SuccessResponseSerializer(serializers.Serializer):
    """
    Generic success response serializer.
    """
    message = serializers.CharField()
    data = serializers.DictField(required=False)


class ErrorResponseSerializer(serializers.Serializer):
    """
    Generic error response serializer.
    """
    error = serializers.CharField()
    details = serializers.DictField(required=False)
