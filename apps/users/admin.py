from django.contrib import admin

from .models import User, Profile, ProfilePhoto, Interest, ProfileInterest
# Register your models here.
admin.site.register(User)
admin.site.register(Profile)
admin.site.register(ProfilePhoto)
admin.site.register(Interest)
admin.site.register(ProfileInterest)    
