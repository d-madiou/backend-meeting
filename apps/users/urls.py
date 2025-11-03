# apps/users/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AuthViewSet, UserViewSet, ProfileViewSet, InterestViewSet

router = DefaultRouter()
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'users', UserViewSet, basename='users')
router.register(r'profile', ProfileViewSet, basename='profile')
router.register(r'interests', InterestViewSet, basename='interests')


urlpatterns = [
    path('', include(router.urls)),
]
