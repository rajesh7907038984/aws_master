"""
Test Django settings for LMS_Project - For testing database connections and functionality
"""

import os
from pathlib import Path
from .base import *
from core.env_loader import get_env, get_bool_env, get_int_env

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Environment identification
ENVIRONMENT = 'test'
DEBUG = True

# Security settings for testing
SECRET_KEY = get_env('DJANGO_SECRET_KEY', 'test-key-for-development-only-not-secure')
ALLOWED_HOSTS = [
    get_env('PRIMARY_DOMAIN', 'localhost'),
    'testserver',
    'localhost',
    '127.0.0.1',
    '*',  # Allow all for testing
]

# AWS RDS Database configuration - Use production credentials for testing
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': get_env('AWS_DB_NAME', 'postgres'),
        'USER': get_env('AWS_DB_USER', 'lms_admin'),
        'PASSWORD': get_env('AWS_DB_PASSWORD'),
        'HOST': get_env('AWS_DB_HOST'),
        'PORT': get_env('AWS_DB_PORT', '5432'),
        'OPTIONS': {
            'connect_timeout': 30,
            'sslmode': 'require',
        },
        'CONN_MAX_AGE': 0,  # Disable connection pooling for testing
    }
}

# Static files configuration - Use environment variables
STATIC_URL = '/static/'
STATIC_ROOT = get_env('STATIC_ROOT', str(BASE_DIR / 'staticfiles_test'))

# Media files configuration - Use environment variables for testing
MEDIA_URL = '/media/'
MEDIA_ROOT = get_env('MEDIA_ROOT', str(BASE_DIR / 'media_test'))
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Session configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_SECURE = False  # HTTP for testing
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 86400
SESSION_SAVE_EVERY_REQUEST = False
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# CSRF configuration for testing
CSRF_COOKIE_SECURE = False  # HTTP for testing
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'

# Cache configuration - Use database cache for testing
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'lms_cache_table',
        'TIMEOUT': 300,
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}

# Logging configuration for testing
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': get_env('LOGS_DIR', str(BASE_DIR / 'logs')) + '/test_errors.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'assignments': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Email configuration for testing
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'test@localhost'

print("🧪 Test settings loaded successfully")