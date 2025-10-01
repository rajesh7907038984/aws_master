"""
Celery app configuration for LMS Project
"""
import os
from celery import Celery
from django.conf import settings

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')

# Create celery app
app = Celery('LMS_Project')

# Configure celery to use Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps
app.autodiscover_tasks()

# Import celery configuration
try:
    from .celery_config import *
    app.conf.update(
        beat_schedule=CELERY_BEAT_SCHEDULE,
        task_routes=CELERY_TASK_ROUTES,
        task_serializer=CELERY_TASK_SERIALIZER,
        result_serializer=CELERY_RESULT_SERIALIZER,
        accept_content=CELERY_ACCEPT_CONTENT,
        result_expires=CELERY_RESULT_EXPIRES,
        task_soft_time_limit=CELERY_TASK_SOFT_TIME_LIMIT,
        task_time_limit=CELERY_TASK_TIME_LIMIT,
        task_max_retries=CELERY_TASK_MAX_RETRIES,
        worker_prefetch_multiplier=CELERY_WORKER_PREFETCH_MULTIPLIER,
        worker_max_tasks_per_child=CELERY_WORKER_MAX_TASKS_PER_CHILD,
    )
except ImportError:
    # Fallback if celery_config is not available
    pass

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
