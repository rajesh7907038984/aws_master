from django.apps import AppConfig

class QuizConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'quiz'
    verbose_name = 'Quiz Management'

    def ready(self):
        """
        Initialize Redis fallback mechanism when app is ready.
        This ensures the Redis fallback is loaded early in the startup process.
        """
        # Import and activate Redis fallback mechanism
        try:
            import core.utils.redis_fallback
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Redis fallback mechanism loaded for quiz app")
        except ImportError:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("WARNING: Redis fallback mechanism could not be loaded for quiz app")
        
        # Import signals to ensure they are registered
        try:
            import quiz.signals
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Quiz signals loaded successfully")
        except ImportError as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to load quiz signals: {e}")