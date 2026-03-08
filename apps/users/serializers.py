"""
User & Profile Serializers
===========================
"""

from rest_framework import serializers
from django.contrib.auth import authenticate
from datetime import date

from .models import User, Profile, ProfilePhoto, Interest, ProfileInterest


# ============================================================================
# AUTHENTICATION SERIALIZERS
# ============================================================================

class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for minimal user registration with Username + PIN.
    """
    pin = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )
    pin_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ['username', 'pin', 'pin_confirm']

    def validate_pin(self, value):
        if not value.isdigit() or len(value) != 4:
            raise serializers.ValidationError('Le PIN doit contenir exactement 4 chiffres.')
        return value

    def validate(self, attrs):
        if attrs['pin'] != attrs['pin_confirm']:
            raise serializers.ValidationError({
                'pin_confirm': 'Les PINs ne correspondent pas.'
            })
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['pin']
        )
        Profile.objects.create(user=user)
        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login using Username + PIN.
    """
    username = serializers.CharField(required=True)
    pin = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )

    def validate_pin(self, value):
        if not value.isdigit() or len(value) != 4:
            raise serializers.ValidationError('Le PIN doit contenir exactement 4 chiffres.')
        return value

    def validate(self, attrs):
        username = attrs.get('username')
        pin = attrs.get('pin')

        if username and pin:
            user = authenticate(
                request=self.context.get('request'),
                username=username,
                password=pin
            )
            if not user:
                raise serializers.ValidationError(
                    'Impossible de se connecter avec les identifiants fournis.',
                    code='authorization'
                )
            if not user.is_active:
                raise serializers.ValidationError(
                    'Le compte utilisateur est désactivé.',
                    code='authorization'
                )
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError(
                'Vous devez inclure le nom d\'utilisateur et le PIN.',
                code='authorization'
            )


# ============================================================================
# PROFILE SERIALIZERS
# ============================================================================

class ProfilePhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProfilePhoto
        fields = ['id', 'url', 'is_primary', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

    def get_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class InterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interest
        fields = ['id', 'name']
        read_only_fields = ['id']


class ProfileInterestSerializer(serializers.ModelSerializer):
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
    age = serializers.IntegerField(read_only=True)
    photos = ProfilePhotoSerializer(many=True, read_only=True)
    interests = ProfileInterestSerializer(many=True, read_only=True)
    is_complete = serializers.BooleanField(read_only=True)
    
    actual_matches = serializers.SerializerMethodField()
    actual_views = serializers.SerializerMethodField()
    actual_messages_sent = serializers.SerializerMethodField()
    
    class Meta:
        model = Profile
        fields = [
            'bio', 'birth_date', 'age', 'gender',
            'city', 'country', 
            'relationship_goal', 'religion', 'looking_for_gender',
            'min_age_preference', 'max_age_preference', 'max_distance_km',
            'profile_completion_percentage', 'is_complete',
            'total_matches', 'profile_views',
            'actual_matches', 'actual_views', 'actual_messages_sent',
            'photos', 'interests',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'profile_completion_percentage', 'total_matches',
            'profile_views',
            'created_at', 'updated_at'
        ]
    
    def get_actual_matches(self, obj):
        from apps.matching.models import Match
        return Match.objects.filter(user=obj.user, is_mutual=True).count()
    
    def get_actual_views(self, obj):
        from apps.matching.models import ProfileView
        return ProfileView.objects.filter(viewed_profile=obj.user).count()
    
    def get_actual_messages_sent(self, obj):
        from apps.messaging.models import Message
        return Message.objects.filter(sender=obj.user).count()


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            'bio', 'birth_date', 'gender',
            'city', 'country',
            'relationship_goal', 'religion', 'looking_for_gender',
            'min_age_preference', 'max_age_preference', 'max_distance_km'
        ]

    def validate_birth_date(self, value):
        if value:
            today = date.today()
            age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
            if age < 18:
                raise serializers.ValidationError('Vous devez avoir au moins 18 ans pour utiliser cette application.')
        return value

    def validate(self, attrs):
        min_age = attrs.get('min_age_preference')
        max_age = attrs.get('max_age_preference')
        if min_age and max_age and min_age > max_age:
            raise serializers.ValidationError({
                'min_age_preference': "L'âge minimum ne peut pas être supérieur à l'âge maximum."
            })
        return attrs

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        instance.calculate_completion_percentage()
        return instance


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    is_profile_complete = serializers.BooleanField(source='profile.is_complete', read_only=True)
    created_at = serializers.DateTimeField(source='profile.created_at', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'is_verified',
            'is_profile_complete', 'last_activity', 'created_at', 'profile'
        ]
        read_only_fields = [
            'id', 'is_verified', 'is_profile_complete', 'last_activity', 'created_at'
        ]


class UserBriefSerializer(serializers.ModelSerializer):
    primary_photo = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'primary_photo', 'age', 'city']

    def get_primary_photo(self, obj):
        request = self.context.get('request')
        primary_photo = obj.profile.photos.filter(is_primary=True).first()
        if primary_photo and request:
            return request.build_absolute_uri(primary_photo.image.url)
        return None

    def get_age(self, obj):
        return getattr(obj.profile, 'age', None)

    def get_city(self, obj):
        return getattr(obj.profile, 'city', None)


class ProfilePhotoUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfilePhoto
        fields = ['image', 'is_primary']

    def validate(self, attrs):
        from django.conf import settings
        profile = self.context['profile']
        current_photo_count = profile.photos.count()
        max_photos = getattr(settings, 'MAX_PROFILE_PHOTOS', 6)
        if current_photo_count >= max_photos:
            raise serializers.ValidationError(
                f'Vous ne pouvez télécharger que jusqu\'à {max_photos} photos.'
            )
        return attrs

    def create(self, validated_data):
        profile = self.context['profile']
        photo = ProfilePhoto.objects.create(profile=profile, **validated_data)
        profile.calculate_completion_percentage()
        return photo


# ============================================================================
# RESPONSE SERIALIZERS
# ============================================================================

class AuthResponseSerializer(serializers.Serializer):
    user = UserSerializer(read_only=True)
    token = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)

class SuccessResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    data = serializers.DictField(required=False)

class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()
    details = serializers.DictField(required=False)
