"""
Migration settings for Tuki project.

These settings are optimized for running Django migrations in Cloud Run Jobs.
"""

from .base import *  # noqa
from decouple import config

# Override database configuration for migrations
# Use Cloud SQL Proxy socket for Cloud Run Jobs
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),  # Cloud SQL Proxy socket
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 0,  # Don't reuse connections for migrations
        'OPTIONS': {
            'sslmode': 'require',
            'connect_timeout': 60,
        },
    }
}

# Disable unnecessary features for migrations
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Minimal logging for migrations
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.db.backends': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
    },
}

# Disable static files collection during migrations
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

print("🔧 MIGRATION SETTINGS: Using direct IP connection to PostgreSQL")
print(f"🔧 DATABASE HOST: {DATABASES['default']['HOST']}")
print(f"🔧 DATABASE NAME: {DATABASES['default']['NAME']}")
