"""
Base Django settings for LMS_Project.
Contains all common settings shared across environments.
"""

import os
import sys
import mimetypes
import warnings
import logging
from pathlib import Path
from django.core.management.utils import get_random_secret_key

logger = logging.getLogger(__name__)

# Suppress Python 3.7 deprecation warnings early
os.environ.setdefault('PYTHONWARNINGS', 'ignore::DeprecationWarning:cryptography,ignore::DeprecationWarning:boto3,ignore::DeprecationWarning:pdfminer,ignore::DeprecationWarning:storages')
warnings.filterwarnings("ignore", category=DeprecationWarning, module="cryptography")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="boto3")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pdfminer")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="storages")

# Load environment variables from unified .env file
from core.env_loader import env_loader, get_env, get_bool_env, get_int_env, get_list_env, validate_environment

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Add the project root to the Python path
sys.path.insert(0, str(BASE_DIR))

# Add proper MIME types for CSS and other static files
mimetypes.add_type("text/css", ".css", True)
mimetypes.add_type("text/css", ".css.map", True)  # CSS source maps
mimetypes.add_type("text/javascript", ".js", True)
mimetypes.add_type("application/javascript", ".js", True)
mimetypes.add_type("application/pdf", ".pdf", True)

# Additional MIME types for better static file handling
mimetypes.add_type("font/woff", ".woff", True)
mimetypes.add_type("font/woff2", ".woff2", True)
mimetypes.add_type("font/ttf", ".ttf", True)
mimetypes.add_type("font/eot", ".eot", True)
mimetypes.add_type("image/svg+xml", ".svg", True)
mimetypes.add_type("image/webp", ".webp", True)

# ==============================================
# MEMORY MANAGEMENT SETTINGS
# ==============================================

# Memory monitoring thresholds (in MB) - OPTIMIZED FOR PRODUCTION
MEMORY_THRESHOLD_MB = get_int_env('MEMORY_THRESHOLD_MB', 1000)  # Critical threshold (optimized for 3.8GB system)
MEMORY_WARNING_THRESHOLD_MB = get_int_env('MEMORY_WARNING_THRESHOLD_MB', 800)  # Warning threshold (optimized)
DASHBOARD_MEMORY_THRESHOLD_MB = get_int_env('DASHBOARD_MEMORY_THRESHOLD_MB', 500)  # Dashboard threshold (optimized)

# PDF processing limits - optimized for memory efficiency
MAX_CONCURRENT_PDF_OPERATIONS = get_int_env('MAX_CONCURRENT_PDF_OPERATIONS', 1)  # Reduced for better memory management

# Additional memory optimization settings
ENABLE_MEMORY_MONITORING = get_bool_env('ENABLE_MEMORY_MONITORING', True)
MEMORY_CLEANUP_INTERVAL = get_int_env('MEMORY_CLEANUP_INTERVAL', 300)  # 5 minutes
MEMORY_GC_THRESHOLD = float(get_env('MEMORY_GC_THRESHOLD', '0.8'))  # Trigger GC at 80% memory usage

# Performance monitoring settings
ENABLE_PERFORMANCE_MONITORING = get_bool_env('ENABLE_PERFORMANCE_MONITORING', True)
PERFORMANCE_MONITORING_INTERVAL = get_int_env('PERFORMANCE_MONITORING_INTERVAL', 60)  # 1 minute
PERFORMANCE_ALERT_THRESHOLD = get_int_env('PERFORMANCE_ALERT_THRESHOLD', 80)  # Alert at 80% threshold


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
        'lms_error': {
            'handlers': ['error_file', 'memory_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'lms_database_error': {
            'handlers': ['error_file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# ==============================================
# CORE DJANGO SETTINGS
# ==============================================

# Session: Use SECRET_KEY from environment variables with enhanced validation
SECRET_KEY = get_env('DJANGO_SECRET_KEY', required=True)

# Enhanced SECRET_KEY validation with comprehensive security checks
try:
    if not SECRET_KEY or len(SECRET_KEY.strip()) == 0:
        raise ValueError("SECRET_KEY cannot be empty")
    
    if len(SECRET_KEY) < 50:
        raise ValueError("SECRET_KEY must be at least 50 characters long for security")
    
    if SECRET_KEY.startswith('django-insecure-'):
        raise ValueError("SECRET_KEY cannot use insecure 'django-insecure-' prefix")
    
    # Check for common weak patterns
    weak_patterns = ['123456', 'password', 'secret', 'key', 'admin']
    if any(pattern in SECRET_KEY.lower() for pattern in weak_patterns):
        logger.warning("SECRET_KEY contains potentially weak patterns")
    
    # Ensure SECRET_KEY has sufficient entropy
    import string
    if not any(c in string.ascii_letters for c in SECRET_KEY):
        raise ValueError("SECRET_KEY must contain letters")
    if not any(c in string.digits for c in SECRET_KEY):
        raise ValueError("SECRET_KEY must contain digits")
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in SECRET_KEY):
        logger.warning("SECRET_KEY should contain special characters for better security")
        
except Exception as e:
    logger.error("SECRET_KEY validation failed")
    raise

logger.info("✅ Using SECRET_KEY from environment variables")
logger.info("   Sessions will persist across server restarts")

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
    'lrs',  # Learning Record Store for xAPI
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
    'scorm',
    
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
    'media_library',
    'sharepoint_integration',
]

# ==============================================
# MIDDLEWARE CONFIGURATION
# ==============================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # ENABLED for development
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',  # RE-ENABLED FOR PROPER CSRF PROTECTION
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.error_logging_middleware.ErrorLoggingMiddleware',  # Enhanced error logging - moved up
    'core.middleware.comprehensive_error_middleware.ComprehensiveErrorMiddleware',  # Comprehensive error handling
    'core.middleware.session_auth_middleware.SessionAuthMiddleware',  # Simplified session recovery
    'scorm.middleware.SCORMAuthenticationMiddleware',  # SCORM authentication for iframe scenarios
    'core.middleware.csp_middleware.CSPMiddleware',  # Content Security Policy with unsafe-eval support
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
                'django.template.context_processors.csrf',  # RE-ADDED for CSRF token support
                'core.context_processors.global_context',
                'core.context_processors.global_sidebar_context',
                'core.context_processors.breadcrumbs',
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

# Use database for session storage for better persistence across deployments
# Database sessions are more reliable than cache-based sessions
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Extended session duration to prevent auto-logout
SESSION_COOKIE_AGE = 604800  # 7 days (extended from 24 hours to reduce logout issues)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keep sessions alive across browser restarts
SESSION_SAVE_EVERY_REQUEST = True  # CRITICAL: Enable session saving for proper login/logout

# Session serialization and security - Use JSONSerializer for better security
SESSION_SERIALIZER = 'django.contrib.sessions.serializers.JSONSerializer'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'  # Changed from None to Lax for better security and compatibility
SESSION_COOKIE_NAME = 'lms_sessionid'  # Custom session cookie name
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_PATH = '/'

# Session security (will be overridden in production settings)
# Note: Secure flag is handled by SECURE_PROXY_SSL_HEADER for ALB deployments
SESSION_COOKIE_SECURE = get_bool_env('SESSION_COOKIE_SECURE', True)  # Default to True for security

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
CSRF_USE_SESSIONS = True  # Use sessions for CSRF tokens for better security
CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript access for AJAX requests
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = get_bool_env('CSRF_COOKIE_SECURE', True)  # Default to True for security
CSRF_TRUSTED_ORIGINS = []  # Will be populated in production settings
CSRF_FAILURE_VIEW = 'core.views.csrf_failure.csrf_failure'  # Use our custom CSRF failure view

# ==============================================
# CORS CONFIGURATION - STANDARDIZED ACROSS ALL ENVIRONMENTS
# ==============================================

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
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
# EMAIL CONFIGURATION
# ==============================================

# OAuth2 Email Configuration for Microsoft 365
OUTLOOK_CLIENT_ID = get_env('OUTLOOK_CLIENT_ID')
OUTLOOK_CLIENT_SECRET = get_env('OUTLOOK_CLIENT_SECRET')
OUTLOOK_TENANT_ID = get_env('OUTLOOK_TENANT_ID')
OUTLOOK_FROM_EMAIL = get_env('OUTLOOK_FROM_EMAIL', get_env('DEFAULT_FROM_EMAIL', 'noreply@example.com'))

# Email Backend - Use OAuth2 if configured, otherwise use Global Admin Settings
if all([OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_TENANT_ID]):
    EMAIL_BACKEND = 'lms_notifications.backends.OutlookOAuth2Backend'
    logger.info(" Using OAuth2 email backend")
else:
    # Use Global Admin Settings for email configuration
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    # Email settings will be configured via Global Admin Settings
    # No hardcoded fallbacks - all email configuration must be done via Global Admin Settings
    logger.info("📧 Email configuration via Global Admin Settings")

DEFAULT_FROM_EMAIL = OUTLOOK_FROM_EMAIL if OUTLOOK_FROM_EMAIL else get_env('DEFAULT_FROM_EMAIL', 'noreply@example.com')

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

# Environment configuration
ENVIRONMENT = get_env('DJANGO_ENV', 'development')

# Primary domain for the application
PRIMARY_DOMAIN = get_env('PRIMARY_DOMAIN', 'localhost:8000')

# Auto-constructs HTTPS URL if not explicitly provided
BASE_URL = get_env('BASE_URL', f'http{"s" if ENVIRONMENT == "production" else ""}://{PRIMARY_DOMAIN}')

# Canonical site URL for external callbacks (used by xAPI launch params)
# Defaults to BASE_URL when SITE_URL is not explicitly set
SITE_URL = get_env('SITE_URL', BASE_URL)

# ==============================================
# ==============================================




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

# Get trusted IPs from environment variables
# Default trusted IPs for local development and admin access
DEFAULT_TRUSTED_IPS = get_list_env('DEFAULT_TRUSTED_IPS', default=[
    '127.0.0.1',
    'localhost'
])

# Add environment-specified trusted IPs
env_trusted_ips = get_list_env('TRUSTED_IPS', default=[])

# Combine default and environment IPs
TRUSTED_IPS = DEFAULT_TRUSTED_IPS + env_trusted_ips

# Content Session Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# CSP configuration moved to middleware


# Note: Individual views can override this with more permissive policies
SECURE_CONTENT_SECURITY_POLICY = None  # Disable default CSP, let middleware handle it
SECURE_CONTENT_SECURITY_POLICY_REPORT_ONLY = False  # Disable CSP report mode

# CSP Configuration for debugging (uncomment to enable CSP violation reporting)
# CSP_REPORT_URI = '/csp-report/'
# CSP_REPORT_ONLY = True  # Set to False once issues are resolved

# HTTPS/SSL Session Settings (addressing Django Session warnings)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = get_bool_env('SECURE_SSL_REDIRECT', False)
# Temporary fix for development - force SSL redirect to False
# Force SSL redirect to False for local development
SECURE_SSL_REDIRECT = False

# ==============================================
# PERFORMANCE OPTIMIZATIONS
# ==============================================

# Template loading optimization
# Use standard template loaders for better performance in production
for template_backend in TEMPLATES:
    if template_backend['BACKEND'] == 'django.template.backends.django.DjangoTemplates':
        if 'loaders' not in template_backend.get('OPTIONS', {}):
            template_backend['APP_DIRS'] = True

# Additional performance settings
DATA_UPLOAD_MAX_NUMBER_FILES = 100
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# File upload size limits (600MB for large SCORM packages)
FILE_UPLOAD_MAX_MEMORY_SIZE = 629145600  # 600MB in bytes
DATA_UPLOAD_MAX_MEMORY_SIZE = 629145600  # 600MB in bytes

# File permissions for uploaded files
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755

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
MEDIA_ROOT = get_env('MEDIA_ROOT', None)  # S3 storage - no local fallback needed

# ==============================================
# CELERY CONFIGURATION
# ==============================================

# NOTE: Celery configuration is centralized in LMS_Project/celery_config.py
# The celery.py file imports and applies all configuration from celery_config.py
# This includes:
# - CELERY_BEAT_SCHEDULE (periodic tasks)
# - CELERY_TASK_ROUTES (task routing)
# - CELERY_TASK_SERIALIZER (serialization settings)
# - Worker settings and performance tuning
#
# To add new periodic tasks or configure Celery, edit:
# /home/ec2-user/lms/LMS_Project/celery_config.py