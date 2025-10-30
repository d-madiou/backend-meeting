# apps/users/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AuthViewSet, UserViewSet, ProfileViewSet

router = DefaultRouter()
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'users', UserViewSet, basename='users')
router.register(r'profile', ProfileViewSet, basename='profile')

urlpatterns = [
    path('', include(router.urls)),
]
