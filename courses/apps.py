from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class CoursesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'courses'

    def ready(self):
        """Run tasks when the app is ready"""
        logger.info("Initializing courses app")
        
        # Import signals to register them
        from . import signals
        from . import signals_certificates
        
        # TinyMCE integration complete
