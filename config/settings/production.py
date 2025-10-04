"""
Production settings for Tuki project.

These settings are suitable for production environment.
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

# Production databases - Use PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
    }
}

# Cache setup - Redis is optional
USE_REDIS = config('USE_REDIS', default=False, cast=bool)
if USE_REDIS:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('REDIS_URL'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'IGNORE_EXCEPTIONS': True,
            }
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    # Use database for cache and sessions (simpler deployment)
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'django_cache_table',
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Static files with Whitenoise and CloudStorage if available
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Rate limiting
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = [
    'rest_framework.throttling.AnonRateThrottle',
    'rest_framework.throttling.UserRateThrottle',
]
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': '50/hour',
    'user': '1000/hour',
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
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
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
    },
}

# Stripe settings
STRIPE_LIVE_MODE = True

# 🚀 GCP CLOUD STORAGE - ENTERPRISE CONFIGURATION
if 'USE_GCP' in os.environ:
    # Google Cloud Storage configuration
    GS_BUCKET_NAME = config('GS_BUCKET_NAME')
    GS_PROJECT_ID = config('GS_PROJECT_ID')
    GS_CREDENTIALS = config('GS_CREDENTIALS', default=None)
    
    # Storage backend for media files
    DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
    
    # Media files configuration
    GS_MEDIA_BUCKET_NAME = config('GS_MEDIA_BUCKET_NAME', default=GS_BUCKET_NAME)
    GS_DEFAULT_ACL = 'publicRead'  # Images need to be publicly accessible
    
    # Cache control for better performance (24 hours)
    GS_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    
    # Custom domain for CDN (optional but recommended for production)
    GS_CUSTOM_ENDPOINT = config('GS_CUSTOM_ENDPOINT', default=None)
    
    # File overwrite behavior - False for unique filenames (better for versioning)
    GS_FILE_OVERWRITE = False
    
    # Media URL configuration
    if GS_CUSTOM_ENDPOINT:
        MEDIA_URL = f"https://{GS_CUSTOM_ENDPOINT}/media/"
    else:
        MEDIA_URL = f"https://storage.googleapis.com/{GS_MEDIA_BUCKET_NAME}/media/"

# AWS S3 settings if deployed on AWS (legacy support)
elif 'USE_AWS' in os.environ:
    # S3 and CloudFront configuration
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default=None)
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    AWS_DEFAULT_ACL = None

    # Media and static storage
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'