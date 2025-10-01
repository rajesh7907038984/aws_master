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
    logger.info("✅ WSGI application initialized successfully")
except Exception as e:
    logger.error(f"❌ WSGI application initialization failed: {e}")
    raise

# Helper functions for runtime directory management
def ensure_media_directories():
    """Create necessary media directories if they don't exist"""
    from django.conf import settings
    import os
    from datetime import datetime, timedelta
    
    try:
        # Get MEDIA_ROOT from settings
        MEDIA_ROOT = getattr(settings, 'MEDIA_ROOT', None)
        if not MEDIA_ROOT:
            logger.info("📁 MEDIA_ROOT not configured, skipping directory creation")
            return
    
        logger.info(f"📁 MEDIA_ROOT: {MEDIA_ROOT}")
    
        # Check if media directory is accessible
        if not os.path.exists(MEDIA_ROOT):
            logger.info(f"📁 Creating MEDIA_ROOT directory: {MEDIA_ROOT}")
            os.makedirs(MEDIA_ROOT, exist_ok=True)
        
        if not os.access(MEDIA_ROOT, os.W_OK):
            logger.warning(f"⚠️ MEDIA_ROOT is not writable: {MEDIA_ROOT}")
            return
    
        # Define required directories
        media_dirs = [
            'course_images', 'course_videos', 'course_content',
            'editor_uploads', 'temp', 'messages/uploads',
            'assignment_content', 'issued_certificates',
            'certificate_templates',
            'temp_uploads', 'exports', 'backups'
        ]
        
        # Create directories
        created_count = 0
        for dir_name in media_dirs:
            dir_path = os.path.join(MEDIA_ROOT, dir_name)
            try:
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                    created_count += 1
                os.chmod(dir_path, 0o755)
            except Exception as e:
                logger.warning(f"⚠️ Failed to create/set permissions for {dir_path}: {e}")
        
        if created_count > 0:
            logger.info(f"📁 Created {created_count} media directories")
        else:
            logger.info("📁 All media directories already exist")
            
    except Exception as e:
        logger.error(f"❌ Error during media directory setup: {e}")
        logger.info("📁 Media directories will be created at runtime when needed")

# Ensure media directories exist at application startup
try:
    ensure_media_directories()
except Exception as e:
    logger.error(f"❌ Media directory setup failed: {e}")
    logger.info("📁 Application will continue - directories created on demand")

logger.info("🎯 WSGI configuration completed successfully")