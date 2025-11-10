# apps/users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AuthViewSet, UserViewSet, ProfileViewSet, InterestViewSet, DeviceTokenViewSet

router = DefaultRouter()
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'users', UserViewSet, basename='users')
router.register(r'profile', ProfileViewSet, basename='profile')
router.register(r'interests', InterestViewSet, basename='interests')

# 🎯 FIX: Group device-tokens under the 'users/' path for correct routing
router.register(r'users/device-tokens', DeviceTokenViewSet, basename='device-tokens') 
# The full URL for this ViewSet is now: /api/users/device-tokens/

urlpatterns = [
    path('', include(router.urls)),
]