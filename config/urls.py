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
from core.views import health_view
from core.og_preview import OGPreviewView
from core.permissions import ApiDocsPermission

urlpatterns = [
    # Health endpoint for Cloud Run. Responde 200 siempre; registra heartbeat de uptime (throttled) si la BD está disponible.
    path('healthz/', health_view),
    
    # Django Admin
    path('admin/', admin.site.urls),
    
    # API URLs - public_urls FIRST so public/destinations/ matches before experiences/public/<slug>
    path('api/v1/', include('api.v1.public_urls')),
    path('api/v1/', include('api.v1.urls')),
    
    # API Documentation (production: superuser JWT required; DEBUG: open)
    path('api/schema/', SpectacularAPIView.as_view(permission_classes=[ApiDocsPermission]), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema', permission_classes=[ApiDocsPermission]), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema', permission_classes=[ApiDocsPermission]), name='redoc'),
    
    # Open Graph preview: SPA index with injected meta for shareable routes (WhatsApp, etc.).
    # Nginx should proxy these paths to Django so crawlers receive server-rendered meta.
    path('erasmus/actividades/entry/<uuid:entry_id>/', OGPreviewView.as_view(), name='og-preview-erasmus-entry'),
    path('alojamientos/<path:slug_or_id>', OGPreviewView.as_view(), name='og-preview-accommodation'),
    path('events/<str:event_id>/', OGPreviewView.as_view(), name='og-preview-event'),
    path('experiences/<path:slug_or_id>', OGPreviewView.as_view(), name='og-preview-experience'),
    path('guias/<path:slug>', OGPreviewView.as_view(), name='og-preview-travel-guide'),

    # 🚀 ENTERPRISE Payment System - LAST to avoid conflicts
    path('', include('payment_processor.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 