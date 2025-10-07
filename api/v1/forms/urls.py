from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FormViewSet, FormResponseViewSet

router = DefaultRouter()
router.register(r'forms', FormViewSet, basename='form')
router.register(r'responses', FormResponseViewSet, basename='form-response')

urlpatterns = [
    path('', include(router.urls)),
]