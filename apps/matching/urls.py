
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FeedViewSet, MatchViewSet


router = DefaultRouter()
router.register(r'feed', FeedViewSet, basename='feed')
router.register(r'discovery', FeedViewSet, basename='discovery')
router.register(r'matches', MatchViewSet, basename='matches')


urlpatterns = [
    path('', include(router.urls)),
]

urlpatterns += [
    path('matching/block/', MatchViewSet.as_view({'post': 'block_user'}), name='block-user'),
]
