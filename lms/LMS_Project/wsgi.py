"""
WSGI config for LMS_Project - Production Only
Simplified configuration for production deployment
"""

import os
import logging
from django.core.wsgi import get_wsgi_application

# Set up logger
logger = logging.getLogger(__name__)

# Set production settings module explicitly
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')

# Get WSGI application
try:
    application = get_wsgi_application()
    logger.info(" WSGI application initialized successfully")
except Exception as e:
    logger.error(f" WSGI application initialization failed: {e}")
    raise

# Helper functions for runtime directory management
def ensure_media_directories():
    """Create necessary media directories if they don't exist"""
    from django.conf import settings
    import os
    from datetime import datetime, timedelta
    
    try:
        # S3 storage - no local directory creation needed
        logger.info(" Using S3 storage - no local MEDIA_ROOT directory creation needed")
        logger.info(f" S3 Bucket: {getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'Not configured')}")
        logger.info(f" S3 Region: {getattr(settings, 'AWS_S3_REGION_NAME', 'Not configured')}")
            
    except Exception as e:
        logger.error(f" Error checking S3 configuration: {e}")

# Ensure media directories exist at application startup
try:
    ensure_media_directories()
except Exception as e:
    logger.error(f" Media directory setup failed: {e}")
    logger.info(" Application will continue - directories created on demand")

logger.info(" WSGI configuration completed successfully")