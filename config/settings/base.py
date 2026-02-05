"""
Base settings for Tuki project.

This module contains settings that are common to all environments.
"""

import os
from pathlib import Path
from decouple import config, Csv
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Security settings
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='http://localhost:8000,http://127.0.0.1:8000', cast=Csv())

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    
    # Third party apps
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'corsheaders',
    'django_filters',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    
    # Our apps
    'apps.users',
    'apps.organizers',
    'apps.events',
    'apps.accommodations',
    'apps.experiences',
    'apps.reservations',
    'apps.payments',
    'apps.forms',
    'apps.satisfaction',  # 🚀 ENTERPRISE: Satisfaction Survey System
    'apps.migration_system',  # 🚀 ENTERPRISE: Backend-to-Backend Migration System
    'apps.ticket_validation',
    'apps.otp',  # 🔐 OTP Authentication System
    'apps.validation',  # 🚀 Enterprise Validation System
    'apps.sync_woocommerce',  # 🚀 ENTERPRISE: WooCommerce Sync System
    'apps.media',  # 🚀 ENTERPRISE: Media Library System
    'apps.whatsapp',  # 🚀 ENTERPRISE: WhatsApp Integration
    'apps.terminal',  # 🚀 ENTERPRISE: Terminal bus schedule management
    'apps.landing_destinations',  # 🚀 ENTERPRISE: Landing destinations (superadmin + public page)
    'apps.creators',  # 🚀 ENTERPRISE: TUKI Creators (influencers)
    'payment_processor',  # 🚀 ENTERPRISE Payment System
    'core',
]

# WooCommerce sync toggle (runtime)
WOOCOMMERCE_SYNC_ENABLED = config('WOOCOMMERCE_SYNC_ENABLED', default=False, cast=bool)

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database - ENTERPRISE CONFIGURATION
# POSTGRESQL ONLY - NO SQLITE FALLBACK
# This will be overridden in cloudrun.py for production
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='tuki_local'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 0,
        'OPTIONS': {
            'sslmode': 'prefer',
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    # {
    #     'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    # },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# JWT settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),     # 8 hours (más tiempo para trabajar sin interrupciones)
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),    # 30 days (más persistencia)
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
    # SLIDING_TOKEN settings comentados (no los estamos usando)
    # 'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    # 'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    # 'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# Django Spectacular settings
SPECTACULAR_SETTINGS = {
    'TITLE': 'Tuki API',
    'DESCRIPTION': 'API for Tuki platform - events, accommodations, experiences',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': True,
    'SCHEMA_PATH_PREFIX': r'/api/v[0-9]',
    'COMPONENT_SPLIT_REQUEST': True,
    'PREPROCESSING_HOOKS': [],
    'POSTPROCESSING_HOOKS': [],
    'SCHEMA_PATH_PREFIX_TRIM': True,
    'DISABLE_ERRORS_AND_WARNINGS': False,
    'COMPONENT_SPLIT_PATCH': False,
    'COMPONENT_SPLIT_RESPONSE': False,
}

# CORS settings
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080',
    cast=Csv()
)

# Add CORS_ALLOW_HEADERS to allow cache-control and other common headers
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

# Allow credentials in CORS requests
CORS_ALLOW_CREDENTIALS = True

# Site ID
SITE_ID = 1

# Auth settings
AUTH_USER_MODEL = 'users.User'

# 🚀 ENTERPRISE EMAIL SETTINGS for Tuki Platform
# Optimizado para latencia <10s end-to-end
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='mail.tuki.cl')
EMAIL_PORT = config('EMAIL_PORT', default=465, cast=int)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=True, cast=bool)  # Port 465 uses SSL
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=False, cast=bool)  # SSL and TLS are mutually exclusive
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='noreply@tuki.cl')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='-W7)HsC<Hsfk')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='Tuki <noreply@tuki.cl>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# 🚀 ENTERPRISE: Email timeout optimizado para velocidad
# Reducido de 30s a 10s para detectar problemas rápidamente
EMAIL_TIMEOUT = 10  # 10 segundos (antes 30s)
EMAIL_SSL_CERTFILE = None
EMAIL_SSL_KEYFILE = None

# Stripe settings
STRIPE_PUBLIC_KEY = config('STRIPE_PUBLIC_KEY', default='')
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')

# Celery settings
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# 🚀 ENTERPRISE PAYMENT SETTINGS
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:8080')

# Transbank WebPay Plus Settings
TRANSBANK_WEBPAY_PLUS_COMMERCE_CODE = config('TRANSBANK_WEBPAY_PLUS_COMMERCE_CODE', default='597055555532')
TRANSBANK_WEBPAY_PLUS_API_KEY = config('TRANSBANK_WEBPAY_PLUS_API_KEY', default='579B532A7440BB0C9079DED94D31EA1615BACEB56610332264630D42D0A36B1C')
TRANSBANK_WEBPAY_PLUS_SANDBOX = config('TRANSBANK_WEBPAY_PLUS_SANDBOX', default=True, cast=bool)

# 🚀 ENTERPRISE: Migration System Configuration
MIGRATION_SYSTEM = {
    'EXPORT_DIR': BASE_DIR / 'exports',
    'CHECKPOINT_DIR': BASE_DIR / 'checkpoints',
    'MAX_EXPORT_SIZE_GB': 10,
    'CHUNK_SIZE': 1000,  # Registros por chunk
    'FILE_CHUNK_SIZE_MB': 10,  # MB por chunk de archivo
    'PARALLEL_TRANSFERS': 5,  # Archivos en paralelo
    'TOKEN_EXPIRY_HOURS': 24,
    'ALLOWED_SOURCE_DOMAINS': [
        'prop.cl',
        'tuki.cl',
        'www.tuki.cl',
        'tukitickets.duckdns.org',
        'localhost',
        '127.0.0.1',
        '*.run.app',  # Cloud Run URLs
    ],
    'VERIFY_SSL': True,  # Verificar certificados SSL en producción
}

# Transbank Oneclick Settings (for future implementation)
TRANSBANK_ONECLICK_COMMERCE_CODE = config('TRANSBANK_ONECLICK_COMMERCE_CODE', default='597055555541')
TRANSBANK_ONECLICK_API_KEY = config('TRANSBANK_ONECLICK_API_KEY', default='579B532A7440BB0C9079DED94D31EA1615BACEB56610332264630D42D0A36B1C')
TRANSBANK_ONECLICK_SANDBOX = config('TRANSBANK_ONECLICK_SANDBOX', default=True, cast=bool) 