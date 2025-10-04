"""
Production Environment Settings for LMS_Project
Extends base settings with production-specific configurations
"""

import os
from pathlib import Path
from .base import *
from core.env_loader import get_env, get_bool_env, get_int_env, get_list_env

# ==============================================
# ENVIRONMENT VARIABLE LOADING
# ==============================================

# Environment variables are now loaded by the unified env_loader in base.py
# No need for manual loading here

# Production-specific context processors (inherits base.py context processors)
# Only override if needed for production-specific fixes

# ==============================================
# PRODUCTION ENVIRONMENT OVERRIDES
# ==============================================

# Environment identification
ENVIRONMENT = 'production'
AWS_DEPLOYMENT = True

# ==============================================
# PRODUCTION SESSION CONFIGURATION OVERRIDES
# ==============================================

# Production-specific session overrides (inherits base.py session config)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Use database for production
SESSION_COOKIE_SECURE = True  # Enable secure cookies for HTTPS
SESSION_SAVE_EVERY_REQUEST = False  # Optimize for production performance

# CSRF configuration - production overrides only
CSRF_COOKIE_SECURE = True  # Enable secure CSRF cookies for production HTTPS

# Disable session corruption warnings
import logging
logging.getLogger('django.contrib.sessions').setLevel(logging.ERROR)

# Production allowed hosts - Use environment variable with fallback
# Get PRIMARY_DOMAIN and ALB_DOMAIN from environment
PRIMARY_DOMAIN = get_env('PRIMARY_DOMAIN', 'localhost')
ALB_DOMAIN = get_env('ALB_DOMAIN', '')

# Build ALLOWED_HOSTS list dynamically
ALLOWED_HOSTS = [
    PRIMARY_DOMAIN,  # Primary production domain from environment
]

# Add ALB domain if configured
if ALB_DOMAIN:
    ALLOWED_HOSTS.append(ALB_DOMAIN)

# Add additional hosts from environment (comma-separated)
additional_hosts = get_list_env('ADDITIONAL_ALLOWED_HOSTS', default=[])
ALLOWED_HOSTS.extend(additional_hosts)

# Add common defaults for production
ALLOWED_HOSTS.extend([
    'localhost',
    '127.0.0.1',
])

# IP blocking configuration
BLOCKED_IPS = []
ALLOW_ALL_IPS = True  # Allow all IPs to access the system

# FIXED: Dynamic IP detection moved to async task to prevent Django startup hangs
# This prevents Chrome connection issues by ensuring Django starts quickly
def add_dynamic_ip_async():
    """Add dynamic IP in background to prevent startup delays"""
    try:
        import requests
        response = requests.get('http://169.254.169.254/latest/meta-data/public-ipv4', timeout=1)
        if response.status_code == 200:
            public_ip = response.text.strip()
            # Use environment variable or cache for dynamic IP
            import os
            os.environ.setdefault('DYNAMIC_PUBLIC_IP', public_ip)
            print(f"🌐 Dynamic public IP detected: {public_ip}")
    except:
        pass  # Silently ignore if metadata service is not available

# Check for cached dynamic IP
if os.environ.get('DYNAMIC_PUBLIC_IP'):
    dynamic_ip = os.environ.get('DYNAMIC_PUBLIC_IP')
    if dynamic_ip not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(dynamic_ip)

# Schedule async IP detection (don't block Django startup)
import threading
threading.Thread(target=add_dynamic_ip_async, daemon=True).start()

# ==============================================
# PRODUCTION DATABASE CONFIGURATION
# ==============================================

# Database configuration - simplified
AWS_DB_PASSWORD = get_env('AWS_DB_PASSWORD')
if not AWS_DB_PASSWORD:
    AWS_DB_PASSWORD = get_env('DATABASE_PASSWORD') or get_env('DB_PASSWORD')
    if not AWS_DB_PASSWORD:
        print("❌ CRITICAL: Database password not found in environment variables")
        print("   Please set AWS_DB_PASSWORD in .env file")
        raise ValueError("Database password is required for production deployment")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': get_env('AWS_DB_NAME', 'postgres'),
        'USER': get_env('AWS_DB_USER', 'lms_admin'),
        'PASSWORD': AWS_DB_PASSWORD,
        'HOST': get_env('AWS_DB_HOST', 'lms-ec2-database.c1wwcwuwq2pa.eu-west-2.rds.amazonaws.com'),
        'PORT': get_env('AWS_DB_PORT', '5432'),
        'OPTIONS': {
            'connect_timeout': 30,
            'sslmode': 'require',
            'application_name': 'LMS_Production',
        },
        'CONN_MAX_AGE': 300,
        'CONN_HEALTH_CHECKS': True,
    }
}
print("🗄️  Using database configuration: {}".format(DATABASES['default']['HOST']))

# ==============================================
# PRODUCTION STATIC FILES CONFIGURATION
# ==============================================

# Override base static root for production - use environment variable
# Fallback uses parent directory to avoid hardcoded paths
STATIC_ROOT = get_env('STATIC_ROOT', str(Path(__file__).resolve().parent.parent.parent.parent / 'lmsstaticfiles'))

# Use local static files storage for better performance
STATICFILES_STORAGE = 'whitenoise.storage.StaticFilesStorage'
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = False  # Disabled for production

# WhiteNoise middleware is configured in base.py

print("📁 Using local static files storage for production (better performance)")

# ==============================================
# SECURITY CONFIGURATION
# ==============================================

# SSL Configuration - ALB handles SSL termination
# Enable SSL redirect since ALB terminates SSL and forwards to HTTP backend
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ==============================================
# PRODUCTION MEDIA FILES CONFIGURATION
# ==============================================

# AWS S3 Configuration for Production
AWS_ACCESS_KEY_ID = get_env('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = get_env('AWS_SECRET_ACCESS_KEY')
# Force the correct bucket name
AWS_STORAGE_BUCKET_NAME = 'lms-staging-nexsy-io'
AWS_S3_REGION_NAME = 'eu-west-2'

# Disable Transfer Acceleration to avoid signature mismatch errors with large uploads
# Using standard S3 endpoint for reliable uploads
AWS_S3_TRANSFER_ACCELERATION = False
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com'

# Force signature version v4 (required for eu-west-2 and Transfer Acceleration)
AWS_S3_SIGNATURE_VERSION = 's3v4'

# Configure boto3 client for S3 (required for django-storages)
# from botocore.client import Config
# AWS_S3_CONFIG = Config(signature_version='s3v4')  # Removed - not supported by django-storages

# S3 Media Storage Settings
# Disable ACL for modern S3 buckets that don't support ACLs
AWS_DEFAULT_ACL = None
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_MEDIA_LOCATION = 'media'
AWS_S3_FILE_OVERWRITE = False

# Additional S3 settings for modern buckets
AWS_S3_ACL = None  # Disable ACL completely
AWS_S3_OBJECT_ACL = None  # Disable object ACL

# Use S3 for media files
DEFAULT_FILE_STORAGE = 'core.s3_storage.MediaS3Storage'
MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/'

# IMPORTANT: When using S3, MEDIA_ROOT should not be set to a local path
# Set to None to ensure all media operations use S3 storage
MEDIA_ROOT = None

print("☁️ Using S3 media storage configuration")
print(f"☁️ MEDIA_URL set to: {MEDIA_URL}")
print(f"☁️ MEDIA_ROOT set to: None (using S3 storage)")

# ==============================================
# PRODUCTION SETTINGS
# ==============================================

# Use standardized CSRF settings from base.py
# CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript access for AJAX requests
# CSRF_COOKIE_SAMESITE = 'Lax'

# Production-specific CORS overrides (inherits base.py CORS config)
# Build CORS_ALLOWED_ORIGINS dynamically from environment
CORS_ALLOWED_ORIGINS = [
    f"https://{PRIMARY_DOMAIN}",
]

# Add ALB domain if configured
if ALB_DOMAIN:
    CORS_ALLOWED_ORIGINS.append(f"https://{ALB_DOMAIN}")
    CORS_ALLOWED_ORIGINS.append(f"http://{ALB_DOMAIN}")  # For health checks

# Add additional CORS origins from environment (comma-separated)
additional_cors = get_list_env('ADDITIONAL_CORS_ORIGINS', default=[])
CORS_ALLOWED_ORIGINS.extend(additional_cors)

# CSRF Configuration - CLEANED UP (Production origins only)
# Note: CSRF_TRUSTED_ORIGINS is defined below in Enhanced CSRF Protection section

# Enhanced CSRF Protection - Production overrides
CSRF_COOKIE_SECURE = True  # Enable secure CSRF cookies for production HTTPS

# Build CSRF_TRUSTED_ORIGINS dynamically from environment
CSRF_TRUSTED_ORIGINS = [
    f'https://{PRIMARY_DOMAIN}',
]

# Add ALB domain if configured
if ALB_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append(f'https://{ALB_DOMAIN}')
    CSRF_TRUSTED_ORIGINS.append(f'http://{ALB_DOMAIN}')  # For health checks

# Add additional CSRF trusted origins from environment (comma-separated)
additional_csrf = get_list_env('ADDITIONAL_CSRF_ORIGINS', default=[])
CSRF_TRUSTED_ORIGINS.extend(additional_csrf)

# Rate limiting configuration
LOGIN_RATE_LIMIT = None  # No rate limiting for real users
LOGIN_RATE_LIMIT_MESSAGE = None  # No rate limiting messages


# ==============================================
# PRODUCTION EMAIL CONFIGURATION OVERRIDES
# ==============================================

# Production-specific email overrides (inherits base.py email config)
# Override only if production needs different email settings

# ==============================================
# PRODUCTION API CONFIGURATION
# ==============================================

# API timeout settings for production
API_TIMEOUT = 30  # 30 seconds for API calls
API_RETRY_ATTEMPTS = 3
API_RETRY_DELAY = 1000  # 1 second base delay

# Enhanced error handling for production
ENABLE_DETAILED_ERROR_LOGGING = True
ENABLE_API_MONITORING = True

# ==============================================
# PRODUCTION LOGGING CONFIGURATION OVERRIDES
# ==============================================

# Production-specific logging overrides (inherits base.py logging config)
# Override only if production needs different logging settings

# ==============================================
# PRODUCTION CELERY CONFIGURATION OVERRIDES
# ==============================================

# Production-specific Celery overrides (inherits base.py Celery config)
CELERY_WORKER_LOGLEVEL = 'WARNING'  # Reduce verbosity in production
CELERY_TASK_ALWAYS_EAGER = False  # Enable async tasks in production

# ==============================================
# PRODUCTION FEATURE FLAGS
# ==============================================

# Production feature flags
ENABLE_EXPERIMENTAL_FEATURES = False
ENABLE_AI_FEATURES = True
ENABLE_ADVANCED_ANALYTICS = True
ENABLE_TEST_DATA_GENERATION = False
ALLOW_UNSAFE_OPERATIONS = False

# Production-specific settings
ENABLE_EXTERNAL_NOTIFICATIONS = True
ENABLE_PAYMENT_PROCESSING = True
ENABLE_EXTERNAL_ANALYTICS = True

# Enable SCORM worker auto-start for production
SCORM_WORKER_AUTO_START = True

# Set DEBUG for production - CRITICAL: Must be False in production
DEBUG = False

# Production-specific security overrides (inherits base.py security config)
# Override only if production needs different security settings

print("🏗️ Production configuration loaded successfully!")
print("🎯 Environment: {}".format(ENVIRONMENT))
print("🐛 Debug mode: {}".format(DEBUG))
print("☁️ S3 Bucket: {}".format(AWS_STORAGE_BUCKET_NAME))
print("🏠 Allowed hosts: {}...".format(', '.join(ALLOWED_HOSTS[:3])))
print("📋 Log directory: {}".format(LOG_DIR or 'Console only'))
# ==============================================
# PRODUCTION SESSION PERSISTENCE OVERRIDES
# ==============================================

# Production-specific session overrides (inherits base.py session config)
# No additional overrides needed - using consistent configuration from base.py

