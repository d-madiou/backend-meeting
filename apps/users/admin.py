from django.contrib import admin

from .models import User, Profile, ProfilePhoto, Interest, ProfileInterest, DeviceToken

# Register your models here.
admin.site.register(User)
admin.site.register(Profile)
admin.site.register(ProfilePhoto)
admin.site.register(Interest)
admin.site.register(ProfileInterest)
admin.site.register(DeviceToken) 


# ==============================================================

from .models import Story, StoryView

@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'story_type', 'view_count', 'created_at', 'expires_at', 'is_expired']
    list_filter = ['story_type', 'created_at']
    search_fields = ['user__username', 'caption']
    readonly_fields = ['view_count', 'created_at', 'expires_at']

@admin.register(StoryView)
class StoryViewAdmin(admin.ModelAdmin):
    list_display = ['story', 'viewer', 'viewed_at']
    list_filter = ['viewed_at']
    search_fields = ['story__user__username', 'viewer__username']
    readonly_fields = ['viewed_at']
