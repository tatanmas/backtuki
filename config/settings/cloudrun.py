"""
Cloud Run settings for Tuki project.

These settings are optimized for Google Cloud Run deployment.
"""

import os
from .base import *  # noqa
from decouple import config, Csv

# Security settings
DEBUG = False
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Cloud Run specific settings
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='*.run.app,tuki.live,www.tuki.live,api.tuki.live,prop.cl',
    cast=Csv()
)
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://*.run.app,https://tuki.live,https://www.tuki.live,https://api.tuki.live,https://prop.cl',
    cast=Csv()
)

# CORS configuration
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='https://tuki.live,https://www.tuki.live,https://api.tuki.live,https://prop.cl',
    cast=Csv()
)
CORS_ALLOW_CREDENTIALS = True

# Database - Cloud SQL ENTERPRISE CONFIGURATION
# POSTGRESQL ONLY - OPTIMIZED FOR HIGH PERFORMANCE
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),  # Cloud SQL Unix socket path
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 300,  # Keep connections for 5 minutes
        'CONN_HEALTH_CHECKS': True,  # Enable health checks
        'OPTIONS': {
            'sslmode': 'disable',  # Unix socket doesn't need SSL
            'connect_timeout': 5,  # Faster timeout
            'application_name': 'tuki-backend-prod',
            'server_side_binding': True,  # Better performance
        },
        'TEST': {
            'NAME': 'test_' + config('DB_NAME'),
        },
    }
}

# Force JSON responses in production to avoid Browsable API static dependencies
# and prevent 500s when DRF tries to render HTML without collected assets.
REST_FRAMEWORK = REST_FRAMEWORK.copy()  # Create a copy to avoid modifying base settings
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
]

# Database connection validation
import logging
logger = logging.getLogger(__name__)
logger.info(f"🔧 ENTERPRISE DB CONFIG: {DATABASES['default']['HOST']}")
logger.info(f"🗄️  DATABASE: {DATABASES['default']['NAME']}")
logger.info(f"👤 USER: {DATABASES['default']['USER']}")
logger.info("🚀 POSTGRESQL ONLY - NO SQLITE FALLBACK")

USE_REDIS = config('USE_REDIS', default=False, cast=bool)
if USE_REDIS:
    # Cache setup with Redis - ENTERPRISE OPTIMIZED
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('REDIS_URL'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 20,
                    'retry_on_timeout': True,
                },
                'SERIALIZER': 'django_redis.serializers.json.JSONSerializer',
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
                'IGNORE_EXCEPTIONS': True,
            },
            'KEY_PREFIX': 'tuki_prod',
            'TIMEOUT': 300,  # 5 minutes default
        }
    }
    # Enable aggressive caching for performance
    CACHE_MIDDLEWARE_ALIAS = 'default'
    CACHE_MIDDLEWARE_SECONDS = 300
    CACHE_MIDDLEWARE_KEY_PREFIX = 'tuki_cache'

    # Session configuration with Redis cache
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    # Fallback to local memory/dummy cache to avoid hard dependency
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tuki-default'
        }
    }
    # Use database-backed sessions when Redis is not available
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'

SESSION_COOKIE_AGE = 86400  # 24 hours

# Static files with Whitenoise - More robust configuration
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = False
WHITENOISE_MANIFEST_STRICT = False  # Prevent 500 errors from missing static files

# 🚀 GCP CLOUD STORAGE - ENTERPRISE CONFIGURATION
DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'

# Google Cloud Storage configuration
GS_BUCKET_NAME = config('GS_BUCKET_NAME')
GS_PROJECT_ID = config('GS_PROJECT_ID')
GS_DEFAULT_ACL = 'publicRead'  # Images need to be publicly accessible

# Cache control for better performance (24 hours)
GS_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}

# File overwrite behavior - False for unique filenames (better for versioning)
GS_FILE_OVERWRITE = False

# Media URL configuration
MEDIA_URL = f"https://storage.googleapis.com/{GS_BUCKET_NAME}/"

# Rate limiting
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = [
    'rest_framework.throttling.AnonRateThrottle',
    'rest_framework.throttling.UserRateThrottle',
]
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': '100/hour',
    'user': '2000/hour',
}

# Logging configuration for Cloud Run
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Stripe settings
STRIPE_LIVE_MODE = config('STRIPE_LIVE_MODE', default=False, cast=bool)

# Celery settings for Cloud Run
CELERY_BROKER_URL = config('REDIS_URL')
CELERY_RESULT_BACKEND = config('REDIS_URL')

# Email settings (ya configuradas en base.py)
# No changes needed

# Frontend URL for Cloud Run
FRONTEND_URL = config('FRONTEND_URL', default='https://tuki.cl')

# Transbank settings for production
TRANSBANK_WEBPAY_PLUS_SANDBOX = config('TRANSBANK_WEBPAY_PLUS_SANDBOX', default=False, cast=bool)
