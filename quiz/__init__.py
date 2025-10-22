# Quiz app initialization
default_app_config = 'quiz.apps.QuizConfig'

# Ensure Redis fallback is loaded
try:
    from core.utils.redis_fallback import *
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Redis fallback mechanism loaded for quiz app")
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("WARNING: Redis fallback mechanism could not be loaded for quiz app")
