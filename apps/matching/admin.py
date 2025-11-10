from django.contrib import admin
from .models import (
    Match, SwipeAction, ProfileView, 
    Block, UserPreference
)

admin.site.register(Match)
admin.site.register(SwipeAction)
admin.site.register(ProfileView)
admin.site.register(Block)
admin.site.register(UserPreference)

