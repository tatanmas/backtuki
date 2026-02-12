"""
Home Server settings for Tuki project.

Settings for deployment on local home server (tukitickets.duckdns.org)
Identical to production but using local storage instead of GCS.
"""

import os
from .base import *  # noqa
from decouple import config, Csv

# Security settings (same as cloudrun)
DEBUG = False
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # Handled by reverse proxy
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Home server specific settings
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='tukitickets.duckdns.org,prop.cl,tuki.cl,localhost,127.0.0.1',
    cast=Csv()
)
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://tukitickets.duckdns.org,https://prop.cl,https://tuki.cl,http://localhost:8000',
    cast=Csv()
)

# CORS configuration
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='https://tuki.live,https://www.tuki.live,https://tuki.cl,https://www.tuki.cl,https://prop.cl',
    cast=Csv()
)
CORS_ALLOW_CREDENTIALS = True

# Database - PostgreSQL (same config as Cloud SQL but local)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 300,
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'connect_timeout': 5,
            'application_name': 'tuki-backend-homeserver',
        },
        'TEST': {
            'NAME': 'test_' + config('DB_NAME'),
        },
    }
}

# Force JSON responses in production
REST_FRAMEWORK = REST_FRAMEWORK.copy()
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
]

# Database connection validation
import logging
logger = logging.getLogger(__name__)
logger.info(f"🏠 HOME SERVER DB CONFIG: {DATABASES['default']['HOST']}")
logger.info(f"🗄️  DATABASE: {DATABASES['default']['NAME']}")
logger.info(f"👤 USER: {DATABASES['default']['USER']}")
logger.info("🚀 POSTGRESQL RUNNING ON HOME SERVER")

USE_REDIS = config('USE_REDIS', default=True, cast=bool)
if USE_REDIS:
    # Cache setup with Redis
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
            'KEY_PREFIX': 'tuki_homeserver',
            'TIMEOUT': 300,
        }
    }
    CACHE_MIDDLEWARE_ALIAS = 'default'
    CACHE_MIDDLEWARE_SECONDS = 300
    CACHE_MIDDLEWARE_KEY_PREFIX = 'tuki_cache'
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'tuki-homeserver'
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'

SESSION_COOKIE_AGE = 86400  # 24 hours

# Static files with Whitenoise
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = False
WHITENOISE_MANIFEST_STRICT = False

# 🏠 LOCAL STORAGE - Use filesystem instead of GCS
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Media files on local filesystem
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

logger.info(f"📁 MEDIA_ROOT: {MEDIA_ROOT}")
logger.info(f"🌐 MEDIA_URL: {MEDIA_URL}")
logger.info("💾 STORAGE: Local Filesystem (not GCS)")

# Rate limiting (same as cloudrun)
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = [
    'rest_framework.throttling.AnonRateThrottle',
    'rest_framework.throttling.UserRateThrottle',
]
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': '500/hour',
    'user': '3000/hour',
}

# Logging configuration
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

# Celery settings
CELERY_BROKER_URL = config('REDIS_URL')
CELERY_RESULT_BACKEND = config('REDIS_URL')

# Backend public URL (media, API base) — must be set in production so media URLs are not localhost
_backend_url = config('BACKEND_URL', default='').strip()
if not _backend_url and not DEBUG:
    # Fallback: use first public host from ALLOWED_HOSTS so destinos/biblioteca no devuelvan localhost
    _hosts = ALLOWED_HOSTS if isinstance(ALLOWED_HOSTS, (list, tuple)) else [h.strip() for h in str(ALLOWED_HOSTS).split(',') if h.strip()]
    for h in _hosts:
        if h and h not in ('*', 'localhost', '127.0.0.1'):
            _backend_url = f"https://{h}"
            break
BACKEND_URL = _backend_url

# Frontend URL
FRONTEND_URL = config('FRONTEND_URL', default='https://tuki.live')

# Transbank settings for production
TRANSBANK_WEBPAY_PLUS_SANDBOX = config('TRANSBANK_WEBPAY_PLUS_SANDBOX', default=False, cast=bool)

# WhatsApp Service URL
WHATSAPP_SERVICE_URL = config('WHATSAPP_SERVICE_URL', default='http://tuki-whatsapp-service:3001')

