"""
config/urls.py - Root URL Configuration
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin site
    path('admin/', admin.site.urls),

    # App-specific API routes
    path('api/', include('apps.users.urls')),
    path('api/', include('apps.matching.urls')),
    

    # DRF browsable API authentication
    path('api-auth/', include('rest_framework.urls')),
    
]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
