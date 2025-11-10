"""
apps/urls.py - Root API URL Configuration for all apps
"""

from django.urls import path, include

urlpatterns = [
    path('', include('apps.users.urls')),
    path('', include('apps.matching.urls')),
]