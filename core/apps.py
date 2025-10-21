from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Core Features'
    
    def ready(self):
        """Import signal handlers when the app is ready"""
        try:
            from core.utils import cache_signals
        except ImportError:
            pass
        
        # Handle dynamic IP detection in production
        self._setup_dynamic_ip_detection()
    
    def _setup_dynamic_ip_detection(self):
        """Setup dynamic IP detection for production environments"""
        try:
            from django.conf import settings
            if hasattr(settings, 'ENVIRONMENT') and settings.ENVIRONMENT == 'production':
                import threading
                import time
                
                def add_dynamic_ip_async():
                    """Add dynamic IP in background after Django is fully loaded"""
                    # Wait a bit to ensure Django is fully initialized
                    time.sleep(2)
                    try:
                        import requests
                        response = requests.get('http://169.254.169.254/latest/meta-data/public-ipv4', timeout=3)
                        if response.status_code == 200:
                            public_ip = response.text.strip()
                            # Add to ALLOWED_HOSTS if not already present
                            if public_ip not in settings.ALLOWED_HOSTS:
                                settings.ALLOWED_HOSTS.append(public_ip)
                                logger.info(f"Dynamic public IP added to ALLOWED_HOSTS: {public_ip}")
                    except Exception as e:
                        logger.debug(f"Dynamic IP detection failed: {e}")
                
                # Start the thread after Django is ready
                threading.Thread(target=add_dynamic_ip_async, daemon=True).start()
                logger.info("Dynamic IP detection thread started")
        except Exception as e:
            logger.error(f"Error setting up dynamic IP detection: {e}")
        