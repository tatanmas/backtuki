"""URL Configuration for Tuki platform."""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from django.http import HttpResponse

urlpatterns = [
    # Health endpoint for Cloud Run (no DB/Redis access) - MUST BE FIRST
    path('healthz/', lambda request: HttpResponse('ok', content_type='text/plain')),
    
    # Django Admin
    path('admin/', admin.site.urls),
    
    # API URLs - Main URLs first, then public URLs to avoid conflicts
    path('api/v1/', include('api.v1.urls')),
    path('api/v1/', include('api.v1.public_urls')),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # 🚀 ENTERPRISE Payment System - LAST to avoid conflicts
    path('', include('payment_processor.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 