from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = "messaging"

# Create a router and register our viewsets with it.
router = DefaultRouter()
router.register(r'conversations', views.ConversationViewSet, basename='conversation')
router.register(r'messages', views.MessageViewSet, basename='message')
router.register(r'wallet', views.CoinWalletViewSet, basename='wallet')

# The API URLs are now determined automatically by the router.
urlpatterns = [
    path('', include(router.urls)),
]