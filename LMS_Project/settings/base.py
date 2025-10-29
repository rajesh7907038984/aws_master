"""
Base Django settings for LMS_Project.
Contains all common settings shared across environments.
"""

import os
import sys
import mimetypes
from pathlib import Path
from django.core.management.utils import get_random_secret_key

# Load environment variables from unified .env file
from core.env_loader import env_loader, get_env, get_bool_env, get_int_env, get_list_env, validate_environment

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Add the project root to the Python path
sys.path.insert(0, str(BASE_DIR))

# Add proper MIME type for CSS files
mimetypes.add_type("text/css", ".css", True)
mimetypes.add_type("text/javascript", ".js", True)
mimetypes.add_type("application/javascript", ".js", True)
mimetypes.add_type("application/pdf", ".pdf", True)

# ==============================================
# MEMORY MANAGEMENT SETTINGS
# ==============================================

# Memory monitoring thresholds (in MB) - OPTIMIZED FOR PRODUCTION
MEMORY_THRESHOLD_MB = get_int_env('MEMORY_THRESHOLD_MB', 800)  # Critical threshold (increased)
MEMORY_WARNING_THRESHOLD_MB = get_int_env('MEMORY_WARNING_THRESHOLD_MB', 600)  # Warning threshold (increased)
DASHBOARD_MEMORY_THRESHOLD_MB = get_int_env('DASHBOARD_MEMORY_THRESHOLD_MB', 400)  # Dashboard threshold

# PDF processing limits
MAX_CONCURRENT_PDF_OPERATIONS = get_int_env('MAX_CONCURRENT_PDF_OPERATIONS', 2)

# Cache timeout for dashboard data (in seconds)
DASHBOARD_CACHE_TIMEOUT = get_int_env('DASHBOARD_CACHE_TIMEOUT', 300)  # 5 minutes

# ==============================================
# LOGGING CONFIGURATION
# ==============================================

# Get logs directory from environment (server-independent)
LOG_DIR = get_env('LOGS_DIR', os.path.join(BASE_DIR, 'logs'))

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'production.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 3,
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'production_errors.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'memory_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'memory_issues.log'),
            'maxBytes': 5 * 1024 * 1024,  # 5MB
            'backupCount': 2,
            'formatter': 'simple',
        },
        'console': {
            'level': 'ERROR',  # Only errors to console
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'error_file'],
            'level': 'WARNING',  # Reduced verbosity
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['error_file'],
            'level': 'ERROR',  # Only log database errors
            'propagate': False,
        },
        'users': {
            'handlers': ['file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'admin_dashboard': {
            'handlers': ['file', 'error_file', 'memory_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'core.memory': {
            'handlers': ['memory_file', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'INFO',
    },
}

# ==============================================
# CORE DJANGO SETTINGS
# ==============================================

# Session: Require SECRET_KEY to be set from environment
SECRET_KEY = get_env('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    # Generate a secure secret key if not provided
    SECRET_KEY = get_random_secret_key()
    print("Generated new SECRET_KEY - set DJANGO_SECRET_KEY environment variable for production")
else:
    # Validate SECRET_KEY length and complexity
    if len(SECRET_KEY) < 50:
        print("SECRET_KEY is too short - generating a secure replacement")
        SECRET_KEY = get_random_secret_key()
    elif SECRET_KEY.startswith('django-insecure-'):
        print("SECRET_KEY uses insecure prefix - generating a secure replacement")
        SECRET_KEY = get_random_secret_key()
    else:
        print("✅ Using provided SECRET_KEY from environment")

# Site framework
SITE_ID = 1

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==============================================
# INSTALLED APPS
# ==============================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',
    'corsheaders',
    'django_extensions',
    
    # Core LMS Apps
    'users',
    'courses',
    'groups',
    'branches',
    'business',
    'branch_portal',
    'LMS_Project',
    'core',
    'admin_dashboard',
    'tinymce_editor',
    
    # Learning & Communication
    'lms_messages',
    'discussions',
    'conferences',
    'categories',
    'quiz',
    'assignments',
    'gradebook',
    'calendar_app',
    'certificates',
    
    # Advanced Features
    'lms_outcomes',
    'lms_rubrics',
    'individual_learning_plan',
    'lms_notifications',
    'course_reviews',
    
    # Management & Integration
    'role_management',
    'reports',
    'account_settings',
    'sharepoint_integration',
    'teams_integration',
]

# ==============================================
# MIDDLEWARE CONFIGURATION
# ==============================================

MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',  # Enable GZIP compression
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',  # RE-ENABLED FOR PROPER CSRF PROTECTION
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ==============================================
# ==============================================

ROOT_URLCONF = 'LMS_Project.urls'

# ==============================================


# ==============================================
# TEMPLATES CONFIGURATION
# ==============================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
            BASE_DIR / 'users' / 'templates',
            BASE_DIR / 'courses' / 'templates',
            BASE_DIR / 'LMS_Project' / 'templates',
            BASE_DIR / 'lms_outcomes' / 'templates',
            BASE_DIR / 'lms_rubrics' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.static',  # ADDED for {% load static %} support
                'django.template.context_processors.csrf',  # RE-ADDED for CSRF token support
                'core.context_processors.global_context',
                'categories.context_processors.categories_processor',
                'courses.context_processors.breadcrumbs',
                'lms_messages.context_processors.messages_context',
                'lms_notifications.context_processors.notifications_context',
                'core.context_processors.sidebar_context',
                'core.context_processors.order_management_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'LMS_Project.wsgi.application'

# ==============================================
# AUTHENTICATION & AUTHORIZATION
# ==============================================

AUTH_USER_MODEL = 'users.CustomUser'

# Auth settings
LOGIN_REDIRECT_URL = '/redirect/'
LOGOUT_REDIRECT_URL = '/login/'
LOGIN_URL = '/login/'

# Enhanced password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        'OPTIONS': {
            'user_attributes': ('username', 'first_name', 'last_name', 'email'),
            'max_similarity': 0.5,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 14,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        'NAME': 'LMS_Project.validators.ComplexPasswordValidator',
    },
]

# ==============================================
# SESSION CONFIGURATION - OPTIMIZED FOR PRODUCTION PERSISTENCE
# ==============================================

# Use Redis for session storage for better persistence across deployments
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_CACHE_ALIAS = 'sessions'  # Use the sessions cache alias defined below

# Extended session duration to prevent auto-logout
SESSION_COOKIE_AGE = 86400  # 24 hours (extended for better user experience)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keep sessions alive across browser restarts
SESSION_SAVE_EVERY_REQUEST = True  # CRITICAL: Enable session saving for proper login/logout

# Session serialization and security
SESSION_SERIALIZER = 'django.contrib.sessions.serializers.JSONSerializer'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_NAME = 'lms_sessionid'  # Custom session cookie name
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_PATH = '/'

# Session security (will be overridden in production settings)
# Note: Secure flag is handled by SECURE_PROXY_SSL_HEADER for ALB deployments
SESSION_COOKIE_SECURE = False  # Set to True in production.py when HTTPS is properly configured

# Session timeout configuration
SESSION_TIMEOUT_REDIRECT = '/login/'  # Redirect to login on session timeout

# ==============================================
# CSRF CONFIGURATION - RE-ENABLED FOR PROPER SECURITY
# ==============================================

CSRF_COOKIE_AGE = 31449600  # 1 year
CSRF_COOKIE_DOMAIN = None  # Use default domain
CSRF_COOKIE_PATH = '/'
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'
CSRF_USE_SESSIONS = False  # Use cookies for CSRF tokens
CSRF_FAILURE_VIEW = 'django.views.csrf.csrf_failure'
CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript access for AJAX requests
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = False  # Set to True in production with HTTPS

# ==============================================
# CORS CONFIGURATION - STANDARDIZED ACROSS ALL ENVIRONMENTS
# ==============================================

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
]

CORS_ALLOWED_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

CORS_ALLOWED_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_PREFLIGHT_MAX_AGE = 86400  # 24 hours

# ==============================================
# CACHE CONFIGURATION
# ==============================================

# Environment-specific Redis configuration
ENVIRONMENT = get_env('DJANGO_ENV', 'development')

# Environment-specific Redis database and key prefix
REDIS_DB_MAP = {
    'development': '1',
    'testing': '2',
    'staging': '2',  # Staging uses separate Redis DB
    'production': '0'
}

# Get Redis database for current environment
redis_db = REDIS_DB_MAP.get(ENVIRONMENT, '1')

# Default Redis URL with environment-specific database
# Use environment variable for Redis URL, with secure fallback
default_redis_url = get_env('REDIS_URL', f'redis://127.0.0.1:6379/{redis_db}')

# Environment-specific cache key prefix
cache_key_prefix = get_env('CACHE_KEY_PREFIX', f'lms_{ENVIRONMENT}_')

CACHES = {
    'default': {
        'BACKEND': 'core.utils.cache_backends.FallbackRedisCache',
        'LOCATION': get_env('REDIS_URL', default_redis_url),
        'OPTIONS': {
            'retry_on_timeout': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'max_connections': 50,
            # Enhanced Redis options for better reliability
            'health_check_interval': 30,
            'retry_on_error': [ConnectionError, TimeoutError]
        },
        'KEY_PREFIX': cache_key_prefix,
        'TIMEOUT': 300,  # 5 minutes default
        'VERSION': 1,  # Cache versioning for invalidation
    },
    'sessions': {
        'BACKEND': 'core.utils.cache_backends.FallbackRedisCache',
        'LOCATION': get_env('REDIS_URL', default_redis_url),
        'OPTIONS': {
            'retry_on_timeout': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'health_check_interval': 30,
            'retry_on_error': [ConnectionError, TimeoutError],
        },
        'KEY_PREFIX': f'{cache_key_prefix}sessions_',
        'TIMEOUT': 1800,  # 30 minutes for sessions
        'VERSION': 1,
    },
    'long_term': {
        'BACKEND': 'core.utils.cache_backends.FallbackRedisCache',
        'LOCATION': get_env('REDIS_URL', default_redis_url),
        'OPTIONS': {
            'retry_on_timeout': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'health_check_interval': 30,
            'retry_on_error': [ConnectionError, TimeoutError],
        },
        'KEY_PREFIX': f'{cache_key_prefix}long_',
        'TIMEOUT': 3600,  # 1 hour for heavy queries
        'VERSION': 1,
    }
}

# ==============================================
# EMAIL CONFIGURATION
# ==============================================

# OAuth2 Email Configuration for Microsoft 365
OUTLOOK_CLIENT_ID = get_env('OUTLOOK_CLIENT_ID')
OUTLOOK_CLIENT_SECRET = get_env('OUTLOOK_CLIENT_SECRET')
OUTLOOK_TENANT_ID = get_env('OUTLOOK_TENANT_ID')
OUTLOOK_FROM_EMAIL = get_env('OUTLOOK_FROM_EMAIL')

# Anthropic API Configuration
ANTHROPIC_API_KEY = get_env('ANTHROPIC_API_KEY')

# Email Backend - Use OAuth2 if configured, otherwise use Global Admin Settings
# Check for valid OAuth2 credentials (not placeholder values)
valid_oauth_credentials = all([
    OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_ID != 'your_outlook_client_id',
    OUTLOOK_CLIENT_SECRET and OUTLOOK_CLIENT_SECRET != 'your_outlook_client_secret', 
    OUTLOOK_TENANT_ID and OUTLOOK_TENANT_ID != 'your_outlook_tenant_id'
])

# Check for valid Anthropic API key (not placeholder values)
valid_anthropic_key = (ANTHROPIC_API_KEY and 
                      ANTHROPIC_API_KEY != 'sk-ant-api03-your_anthropic_api_key_here' and
                      ANTHROPIC_API_KEY != 'your_anthropic_api_key_here')

if valid_oauth_credentials:
    EMAIL_BACKEND = 'lms_notifications.backends.OutlookOAuth2Backend'
    print("✅ Using OAuth2 email backend")
else:
    # Use Global Admin Settings for email configuration
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    # Email settings will be configured via Global Admin Settings
    # No hardcoded fallbacks - all email configuration must be done via Global Admin Settings
    print("📧 Email configuration via Global Admin Settings")

DEFAULT_FROM_EMAIL = get_env('DEFAULT_FROM_EMAIL', OUTLOOK_FROM_EMAIL if OUTLOOK_FROM_EMAIL else f"noreply@{get_env('PRIMARY_DOMAIN', 'localhost')}")

# ==============================================
# INTERNATIONALIZATION
# ==============================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ==============================================
# DOMAIN & URL CONFIGURATION
# ==============================================

# Primary domain for the application
PRIMARY_DOMAIN = get_env('PRIMARY_DOMAIN', 'localhost:8000')

# Base URL for the application (used for email links, etc.)
# Auto-constructs HTTPS URL if not explicitly provided
BASE_URL = get_env('BASE_URL', f'http{"s" if ENVIRONMENT == "production" else ""}://{PRIMARY_DOMAIN}')

# ==============================================
# AI INTEGRATION (ANTHROPIC)
# ==============================================

ANTHROPIC_API_KEY = get_env('ANTHROPIC_API_KEY')
ANTHROPIC_MODEL = get_env('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
ANTHROPIC_MAX_TOKENS = get_int_env('ANTHROPIC_MAX_TOKENS', 1000)

# ==============================================
# THIRD-PARTY INTEGRATIONS
# ==============================================

# Postcode Lookup Configuration
IDEAL_POSTCODES_API_KEY = get_env('IDEAL_POSTCODES_API_KEY')

# ==============================================
# Session SETTINGS
# ==============================================

# Default trusted IPs for local development and admin access
DEFAULT_TRUSTED_IPS = [
    # Local development IPs
    # Public IP addresses for admin access
    '103.149.158.14',  # IPv4 public IP
    '2403:a080:1d:dca1:2006:c571:7bd3:6472',  # IPv6 public IP
    '2403:a080:1d:dca1:1884:1e4c:2cff:2e6a'  # IPv6 public IP (previous)
]

# Add environment-specified trusted IPs
env_trusted_ips = get_list_env('TRUSTED_IPS', default=[])

# Combine default and environment IPs
TRUSTED_IPS = DEFAULT_TRUSTED_IPS + env_trusted_ips

# Content Session Settings
X_FRAME_OPTIONS = 'SAMEORIGIN'  # Allow iframes from same origin
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Content Security Policy
# Note: Individual views can override this with more permissive policies
SECURE_CONTENT_SECURITY_POLICY = None  # Disable default CSP, let views handle it

# HTTPS/SSL Session Settings (addressing Django Session warnings)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = get_bool_env('SECURE_SSL_REDIRECT', False)

# ==============================================
# PERFORMANCE OPTIMIZATIONS
# ==============================================

# Template loading optimization
# Cache template loaders for better performance in production
for template_backend in TEMPLATES:
    if template_backend['BACKEND'] == 'django.template.backends.django.DjangoTemplates':
        if 'loaders' not in template_backend.get('OPTIONS', {}):
            template_backend['APP_DIRS'] = False
            template_backend.setdefault('OPTIONS', {})['loaders'] = [
                ('django.template.loaders.cached.Loader', [
                    'django.template.loaders.filesystem.Loader',
                    'django.template.loaders.app_directories.Loader',
                ]),
            ]

# Additional performance settings
DATA_UPLOAD_MAX_NUMBER_FILES = 100
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# File permissions for uploaded files
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755

# Large file upload support (1GB+)
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024 * 1024   # 2GB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# Temporary file handling for large uploads
FILE_UPLOAD_TEMP_DIR = get_env('FILE_UPLOAD_TEMP_DIR', '/tmp')
FILE_UPLOAD_HANDLERS = [
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',
]

# ==============================================
# STATIC FILES CONFIGURATION
# ==============================================

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
# Use environment variable for static root (server-independent)
STATIC_ROOT = get_env('STATIC_ROOT', str(BASE_DIR.parent / 'lmsstaticfiles'))

# Static files directories - where Django will look for static files
STATICFILES_DIRS = [
    BASE_DIR / 'static',  # Main static directory
]

# Static files finders
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# ==============================================
# MEDIA FILES CONFIGURATION  
# ==============================================

# Media files (uploads) - Using S3 Storage
# Note: S3 configuration is handled in production/simplified settings
# This is a fallback for development
MEDIA_URL = '/media/'
# Use environment variable for media root (server-independent)
MEDIA_ROOT = get_env('MEDIA_ROOT', str(BASE_DIR / 'media_local'))  # Fallback for development only

# ==============================================
# CELERY CONFIGURATION
# ==============================================

# Enable synchronous task execution for development/testing
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Conditional celery import to avoid import errors during deployment
try:
    from celery.schedules import crontab
    
    CELERY_BEAT_SCHEDULE = {
        'sync-gradebook-daily': {
            'task': 'gradebook.tasks.sync_gradebook',
            'schedule': crontab(hour=2, minute=0),  # Run at 2 AM every day
            'args': (),
        },
    }
except ImportError:
    # Fallback when celery is not available
    CELERY_BEAT_SCHEDULE = {}