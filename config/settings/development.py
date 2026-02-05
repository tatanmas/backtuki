"""
Development settings for Tuki project.

These settings are suitable for local development environment.
"""

from .base import *  # noqa

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Django Debug Toolbar
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
INTERNAL_IPS = ['127.0.0.1']

# ✅ Configurar Debug Toolbar para no interferir con API endpoints
DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: (
        DEBUG and 
        request.META.get('REMOTE_ADDR') in INTERNAL_IPS and
        not request.path.startswith('/api/')  # ✅ Excluir rutas de API
    ),
}

# 🚀 ENTERPRISE EMAIL CONFIGURATION for Tuki
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'mail.tuki.cl'
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_USE_TLS = False  # SSL and TLS are mutually exclusive
EMAIL_HOST_USER = 'noreply@tuki.cl'
EMAIL_HOST_PASSWORD = '-W7)HsC<Hsfk'
DEFAULT_FROM_EMAIL = 'Tuki <noreply@tuki.cl>'
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Database - Use PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='tuki_db'),
        'USER': config('DB_USER', default='tuki_user'),
        'PASSWORD': config('DB_PASSWORD', default='tuki_password'),
        'HOST': config('DB_HOST', default='db'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# Allow backend host for Docker internal communication
ALLOWED_HOSTS = list(ALLOWED_HOSTS) + ['backend']

# Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Static files
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# 🚀 ENTERPRISE: Use Google Cloud Storage in development too for consistency
# This ensures we test the same storage backend locally as in production
USE_GCS_IN_DEV = config('USE_GCS_IN_DEV', default=False, cast=bool)

if USE_GCS_IN_DEV:
    # Use Google Cloud Storage with custom backend
    DEFAULT_FILE_STORAGE = 'core.storage.PublicGoogleCloudStorage'
    
    # Google Cloud Storage configuration
    GS_BUCKET_NAME = config('GS_BUCKET_NAME')
    GS_PROJECT_ID = config('GS_PROJECT_ID', default=None)
    
    # 🚀 ENTERPRISE: Use credentials file if available, otherwise use ADC
    import os
    credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    GS_CREDENTIALS = None
    
    if credentials_path and os.path.exists(credentials_path):
        try:
            from google.oauth2 import service_account
            from google.auth import exceptions as auth_exceptions
            try:
                GS_CREDENTIALS = service_account.Credentials.from_service_account_file(credentials_path)
            except (auth_exceptions.MalformedError, ValueError, KeyError) as e:
                # Credentials file is malformed or invalid, use ADC
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"⚠️ [DEV] GCS credentials file invalid ({e}), using ADC")
                GS_CREDENTIALS = None
        except ImportError:
            # google.oauth2 not available, use ADC
            GS_CREDENTIALS = None
    
    # 🚀 ENTERPRISE: No ACL needed - bucket has uniform bucket-level access enabled
    GS_DEFAULT_ACL = None
    
    # Cache control for better performance
    GS_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    
    # File overwrite behavior
    GS_FILE_OVERWRITE = False
    
    # Media URL configuration
    MEDIA_URL = f"https://storage.googleapis.com/{GS_BUCKET_NAME}/"
else:
    # Use local file storage
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    
    # Ensure media settings for local development
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True  # In development only
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    'GET',
    'POST',
    'PUT',
    'PATCH',
    'DELETE',
    'OPTIONS',
]
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-tenant',  # 🚀 ENTERPRISE: Multi-tenant header for payment processing
    'cache-control',
    'pragma',
]

# Set token timeout to the future for development (30 days)
TOKEN_EXPIRED_AFTER_SECONDS = 60 * 60 * 24 * 30

# Dev specific settings for Django REST Framework
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': '1000/day',
    'user': '10000/day',
}

# CSRF settings for development
CSRF_TRUSTED_ORIGINS = ['http://localhost:8080', 'http://localhost:8081', 'http://localhost:8000']
CSRF_COOKIE_SECURE = False
CSRF_USE_SESSIONS = False
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = None  # Needed for cross-origin requests

# 🚀 ENTERPRISE: Override frontend URL for development
FRONTEND_URL = 'http://localhost:8080'

# 🚨 CRÍTICO: Deshabilitar emails durante migraciones de WooCommerce
MIGRATION_MODE = True

# 🚀 WhatsApp Service URL
WHATSAPP_SERVICE_URL = config('WHATSAPP_SERVICE_URL', default='http://whatsapp-service:3001')