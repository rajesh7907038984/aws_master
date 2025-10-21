"""
LMS Project Django Application
"""

# Ensure celery app is always imported when Django starts
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Fallback if celery is not available
    pass
