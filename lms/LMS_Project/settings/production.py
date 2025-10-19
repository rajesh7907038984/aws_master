"""
Production Environment Settings for LMS_Project
Extends base settings with production-specific configurations
"""

import os
import logging
from pathlib import Path
from .base import *
from core.env_loader import get_env, get_bool_env, get_int_env, get_list_env

logger = logging.getLogger(__name__)

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
# Only override settings that are different from base.py
SESSION_COOKIE_SECURE = True  # Enable secure cookies for HTTPS

# CSRF configuration - production overrides only
CSRF_COOKIE_SECURE = True  # Enable secure CSRF cookies for production HTTPS

# Disable session corruption warnings
import logging
logging.getLogger('django.contrib.sessions').setLevel(logging.ERROR)

# ==============================================
# CACHE CONFIGURATION
# ==============================================
# Use database cache for production reliability
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'lms_cache_table',
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
            'CULL_FREQUENCY': 3,
        }
    }
}

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

# Add test server for Django test client (development only)
if get_env('DJANGO_ENV', 'production') == 'development':
    ALLOWED_HOSTS.extend([
        'localhost',
        '127.0.0.1',
        'testserver',  # For Django test client
    ])

# Always add localhost for local testing and development
ALLOWED_HOSTS.extend([
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
])

# IP blocking configuration
BLOCKED_IPS = []
ALLOW_ALL_IPS = get_bool_env('ALLOW_ALL_IPS', False)  # Restrict IP access by default

# Dynamic IP detection - moved to AppConfig ready() method for proper Django lifecycle
# This prevents startup issues and ensures proper Django application initialization
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
            logger.info(f"Dynamic public IP detected: {public_ip}")
    except Exception as e:
        logger.debug(f"Metadata service not available: {e}")
        # Log the specific error for debugging
        logger.info(f"Dynamic IP detection failed: {type(e).__name__}: {e}")

# Check for cached dynamic IP
if os.environ.get('DYNAMIC_PUBLIC_IP'):
    dynamic_ip = os.environ.get('DYNAMIC_PUBLIC_IP')
    if dynamic_ip not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(dynamic_ip)
        logger.info(f"Added cached dynamic IP to ALLOWED_HOSTS: {dynamic_ip}")

# Note: Dynamic IP detection is now handled in core/apps.py AppConfig.ready() method
# This ensures proper Django application lifecycle and prevents startup issues

# ==============================================
# PRODUCTION DATABASE CONFIGURATION
# ==============================================

# Database configuration - enhanced with comprehensive error handling
try:
    # Try multiple environment variable names for database password
    AWS_DB_PASSWORD = get_env('AWS_DB_PASSWORD')
    if not AWS_DB_PASSWORD:
        AWS_DB_PASSWORD = get_env('DATABASE_PASSWORD') or get_env('DB_PASSWORD')
    
    if not AWS_DB_PASSWORD:
        # Try to get from alternative sources
        import os
        AWS_DB_PASSWORD = os.environ.get('POSTGRES_PASSWORD') or os.environ.get('DB_PASS')
        
    if not AWS_DB_PASSWORD:
        logger.error("Database password not found in any environment variable")
        logger.error("Checked: AWS_DB_PASSWORD, DATABASE_PASSWORD, DB_PASSWORD, POSTGRES_PASSWORD, DB_PASS")
        raise ValueError("Database password is required for production deployment. Please set AWS_DB_PASSWORD in .env file")
    
    # Validate password strength
    if len(AWS_DB_PASSWORD) < 8:
        logger.warning("Database password is shorter than recommended (8 characters)")
    
    logger.info("Database password found and validated")
    
except Exception as e:
    logger.error(f"Database configuration error: {e}")
    logger.error("Please ensure AWS_DB_PASSWORD is set in your .env file")
    raise

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': get_env('AWS_DB_NAME', 'postgres'),
        'USER': get_env('AWS_DB_USER', 'lms_admin'),
        'PASSWORD': AWS_DB_PASSWORD,
        'HOST': get_env('AWS_DB_HOST', required=True),
        'PORT': get_env('AWS_DB_PORT', '5432'),
        'OPTIONS': {
            'connect_timeout': 30,
            'sslmode': 'require',
            'application_name': 'LMS_Production',
        },
        'CONN_MAX_AGE': 300,
        'CONN_HEALTH_CHECKS': True,
        'ATOMIC_REQUESTS': True,  # Ensure database transactions are atomic
    }
}
# Database configuration loaded

# ==============================================
# PRODUCTION STATIC FILES CONFIGURATION - WHITENOISE
# ==============================================

# Override base static root for production - use environment variable
# Fallback uses parent directory to avoid hardcoded paths
STATIC_ROOT = get_env('STATIC_ROOT', str(Path(__file__).resolve().parent.parent.parent.parent / 'lmsstaticfiles'))

# Use WhiteNoise for static file serving (better than nginx for Django apps)
STATICFILES_STORAGE = 'whitenoise.storage.StaticFilesStorage'

# WhiteNoise configuration - ENABLED for proper static file serving
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
WHITENOISE_INDEX_FILE = True
WHITENOISE_ADD_HEADERS_FUNCTION = 'core.utils.whitenoise_headers.whitenoise_headers'

# Static files compression and caching
WHITENOISE_MAX_AGE = 31536000  # 1 year
WHITENOISE_SKIP_COMPRESS_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'zip', 'gz', 'mp4', 'webm', 'ogg']

# WhiteNoise middleware is configured in base.py

logger.info("✅ Using WhiteNoise for static file serving (optimized for Django)")

# ==============================================
# SECURITY CONFIGURATION
# ==============================================

# SSL Configuration - ALB handles SSL termination
# Enable SSL redirect since ALB terminates SSL and forwards to HTTP backend
# Enabled for security - ALB handles SSL termination properly
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Let individual views control X-Frame-Options rather than applying globally
# X_FRAME_OPTIONS = 'DENY'  # DISABLED - Let views control this


# ==============================================
# PRODUCTION MEDIA FILES CONFIGURATION - S3 STORAGE
# ==============================================

# S3 Storage Configuration
AWS_ACCESS_KEY_ID = get_env('AWS_ACCESS_KEY_ID', required=True)
AWS_SECRET_ACCESS_KEY = get_env('AWS_SECRET_ACCESS_KEY', required=True)
AWS_STORAGE_BUCKET_NAME = get_env('AWS_STORAGE_BUCKET_NAME', required=True)
AWS_S3_REGION_NAME = get_env('AWS_S3_REGION_NAME', 'us-east-1')
AWS_S3_CUSTOM_DOMAIN = get_env('AWS_S3_CUSTOM_DOMAIN', None)
AWS_DEFAULT_ACL = 'private'
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=2592000',  # 30 days for better caching
    'ContentDisposition': 'inline',  # Allow inline viewing
}

# Video streaming support
AWS_S3_OBJECT_PARAMETERS_VIDEO = {
    'CacheControl': 'max-age=31536000',  # 1 year for videos
    'ContentDisposition': 'inline',
    'ContentType': 'video/mp4',
}

AWS_S3_FILE_OVERWRITE = False
AWS_S3_VERIFY = True

# Use S3 for media files
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

# Add CloudFront CDN support (if available)
AWS_S3_CUSTOM_DOMAIN = get_env('CLOUDFRONT_DOMAIN', None)
if AWS_S3_CUSTOM_DOMAIN:
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
    SCORM_MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/elearning/'
else:
    MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/media/'
    SCORM_MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/elearning/'

# Security settings for S3 media files
FILE_UPLOAD_PERMISSIONS = 0o644  # Readable by owner and group, writable by owner
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755  # Readable and executable by all, writable by owner

# Media file security settings
MEDIA_FILE_MAX_SIZE = 600 * 1024 * 1024  # 600MB max file size for large ZIP files
ALLOWED_MEDIA_EXTENSIONS = [
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',  # Images
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm',   # Videos
    '.pdf', '.doc', '.docx', '.txt', '.rtf',           # Documents
    '.mp3', '.wav', '.ogg', '.m4a',                    # Audio
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',     # Archives (including ZIP)
]

# Compliance settings for S3 storage
ENABLE_FILE_ENCRYPTION = get_bool_env('ENABLE_FILE_ENCRYPTION', False)
ENABLE_AUDIT_LOGGING = get_bool_env('ENABLE_AUDIT_LOGGING', True)
ENABLE_FILE_QUARANTINE = get_bool_env('ENABLE_FILE_QUARANTINE', False)

# Large file upload settings (600MB support) - optimized for S3 streaming
# Note: Files larger than FILE_UPLOAD_MAX_MEMORY_SIZE will be streamed to temp disk,
# then uploaded to S3. This prevents memory issues with large SCORM packages.
DATA_UPLOAD_MAX_MEMORY_SIZE = 650 * 1024 * 1024  # 650MB - allow 600MB SCORM files
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10MB in memory, larger files to temp disk

# Temporary file handling for large uploads - use /tmp with sufficient space
FILE_UPLOAD_TEMP_DIR = get_env('FILE_UPLOAD_TEMP_DIR', '/tmp')
FILE_UPLOAD_HANDLERS = [
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',  # Large files to temp
    'django.core.files.uploadhandler.MemoryFileUploadHandler',      # Small files in memory
]

logger.info("☁️ Using S3 media storage configuration")
logger.info("☁️ S3 Bucket: {}".format(AWS_STORAGE_BUCKET_NAME))
logger.info("☁️ S3 Region: {}".format(AWS_S3_REGION_NAME))
logger.info("☁️ MEDIA_URL set to: {}".format(MEDIA_URL))
logger.info("🔒 Compliance features: Audit logging enabled, file permissions secured")
logger.info("📁 Max file size: {}MB (ZIP files supported)".format(MEDIA_FILE_MAX_SIZE // (1024*1024)))

# ==============================================
# PRODUCTION SETTINGS
# ==============================================

# Use standardized CSRF settings from base.py
# CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript access for AJAX requests
# CSRF_COOKIE_SAMESITE = 'Lax'

# Production-specific CORS overrides (inherits base.py CORS config)
# Build CORS_ALLOWED_ORIGINS dynamically from environment
CORS_ALLOWED_ORIGINS = [
    "https://{}".format(PRIMARY_DOMAIN),
]

# Add ALB domain if configured
if ALB_DOMAIN:
    CORS_ALLOWED_ORIGINS.append("https://{}".format(ALB_DOMAIN))
    # Remove HTTP origins for production security

# Add additional CORS origins from environment (comma-separated)
additional_cors = get_list_env('ADDITIONAL_CORS_ORIGINS', default=[])
CORS_ALLOWED_ORIGINS.extend(additional_cors)

# CSRF Configuration - CLEANED UP (Production origins only)
# Note: CSRF_TRUSTED_ORIGINS is defined below in Enhanced CSRF Protection section

# Enhanced CSRF Protection - Production overrides
CSRF_COOKIE_SECURE = True  # Enable secure CSRF cookies for production HTTPS

# Build CSRF_TRUSTED_ORIGINS dynamically from environment
CSRF_TRUSTED_ORIGINS = [
    'https://{}'.format(PRIMARY_DOMAIN),
]

# Add ALB domain if configured
if ALB_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append('https://{}'.format(ALB_DOMAIN))
    # Remove HTTP origins for production security

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


# Set DEBUG for production - CRITICAL: Must be False in production
DEBUG = False

# Production-specific security overrides (inherits base.py security config)
# Override only if production needs different security settings

# Production configuration loaded successfully
logger.info("🏗️ Production configuration loaded successfully!")
logger.info(" Environment: {}".format(ENVIRONMENT))
logger.info("🐛 Debug mode: {}".format(DEBUG))
logger.info("☁️ Media storage: S3 (Amazon Web Services)")
logger.info("🏠 Allowed hosts: {}...".format(', '.join(ALLOWED_HOSTS[:3])))
logger.info(" Log directory: {}".format(LOG_DIR or 'Console only'))
# ==============================================
# PRODUCTION SESSION PERSISTENCE OVERRIDES
# ==============================================

# Production-specific session overrides (inherits base.py session config)
# No additional overrides needed - using consistent configuration from base.py

