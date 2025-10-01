from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class ScormCloudConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scorm_cloud'
    verbose_name = 'SCORM Cloud'

    def ready(self):
        # Direct upload system - no signals needed
        # import scorm_cloud.signals  # REMOVED - using direct upload
        # import scorm_cloud.signals_auto_link  # REMOVED - using direct upload
        import sys
        import os
        
        # Skip worker start during management commands
        skip_conditions = [
            'migrate' in sys.argv,
            'makemigrations' in sys.argv,
            'collectstatic' in sys.argv,
            'shell' in sys.argv,
            'test' in sys.argv,
        ]
        
        if any(skip_conditions):
            logger.info("Skipping SCORM worker auto-start due to management command")
            return
        
        # CRITICAL FIX: Only start worker in the main process, not in Gunicorn worker processes
        # Check if we're in a Gunicorn worker process
        if hasattr(os.environ, 'SERVER_SOFTWARE') and 'gunicorn' in os.environ.get('SERVER_SOFTWARE', ''):
            logger.info("Skipping SCORM worker auto-start in Gunicorn worker process")
            return
        
        # Additional check for Gunicorn worker processes
        if 'gunicorn' in sys.argv[0] or any('gunicorn' in arg for arg in sys.argv):
            logger.info("Skipping SCORM worker auto-start in Gunicorn process")
            return
        
        # PRODUCTION FIX: Force auto-start in production environments
        from django.conf import settings
        environment = getattr(settings, 'ENVIRONMENT', 'local')
        is_production = environment in ['production']
        
        # Default to True for production, configurable for other environments
        auto_start = getattr(settings, 'SCORM_WORKER_AUTO_START', True if is_production else True)
        
        if auto_start:
            try:
                from scorm_cloud.utils.async_uploader import ensure_worker_running
                ensure_worker_running()
                if is_production:
                    logger.info(f"SCORM Cloud async worker started AUTOMATICALLY for {environment} environment")
                else:
                    logger.info("SCORM Cloud async worker started on Django startup")
            except Exception as e:
                logger.error(f"Failed to start SCORM async worker on startup: {str(e)}")
                logger.error("SCORM uploads will NOT work properly! This is a critical error.")
                # In production, try one more time after a brief delay
                if is_production:
                    import time
                    time.sleep(2)
                    try:
                        from scorm_cloud.utils.async_uploader import ensure_worker_running
                        ensure_worker_running()
                        logger.info("SCORM Cloud async worker started on second attempt")
                    except Exception as e2:
                        logger.error(f"Second attempt to start SCORM worker also failed: {str(e2)}")
        else:
            logger.warning("SCORM worker auto-start disabled. Use 'manage.py scorm_worker start' to start manually")
