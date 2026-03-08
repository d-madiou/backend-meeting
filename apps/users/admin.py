from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Profile, ProfilePhoto, Interest, ProfileInterest

# ==========================================
# Register User Model
# ==========================================
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['username', 'email', 'is_verified', 'is_active']
    search_fields = ['username', 'email']
    ordering = ['username']
    
    # Standard UserAdmin fieldsets
    fieldsets = UserAdmin.fieldsets
    add_fieldsets = UserAdmin.add_fieldsets

admin.site.register(User, CustomUserAdmin)

# ==========================================
# Register Profile Models
# ==========================================
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'gender', 'city', 'relationship_goal', 'profile_completion_percentage']
    list_filter = ['gender', 'relationship_goal', 'marital_status']
    search_fields = ['user__username', 'city', 'profession']

@admin.register(ProfilePhoto)
class ProfilePhotoAdmin(admin.ModelAdmin):
    list_display = ['profile', 'is_primary', 'uploaded_at']

@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ['name']

@admin.register(ProfileInterest)
class ProfileInterestAdmin(admin.ModelAdmin):
    list_display = ['profile', 'interest', 'passion_level']