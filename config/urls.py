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

from core.og_preview import OGPreviewView

urlpatterns = [
    # Health endpoint for Cloud Run (no DB/Redis access) - MUST BE FIRST
    path('healthz/', lambda request: HttpResponse('ok', content_type='text/plain')),
    
    # Django Admin
    path('admin/', admin.site.urls),
    
    # API URLs - public_urls FIRST so public/destinations/ matches before experiences/public/<slug>
    path('api/v1/', include('api.v1.public_urls')),
    path('api/v1/', include('api.v1.urls')),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # Open Graph preview: SPA index with injected meta for shareable routes (WhatsApp, etc.).
    # Nginx should proxy these paths to Django so crawlers receive server-rendered meta.
    path('erasmus/actividades/entry/<uuid:entry_id>/', OGPreviewView.as_view(), name='og-preview-erasmus-entry'),
    path('alojamientos/<path:slug_or_id>', OGPreviewView.as_view(), name='og-preview-accommodation'),
    path('events/<str:event_id>/', OGPreviewView.as_view(), name='og-preview-event'),
    path('experiences/<path:slug_or_id>', OGPreviewView.as_view(), name='og-preview-experience'),
    
    # 🚀 ENTERPRISE Payment System - LAST to avoid conflicts
    path('', include('payment_processor.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 