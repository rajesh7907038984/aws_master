from celery import shared_task
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)

@shared_task
def sync_gradebook():
    """
    Celery task to sync assignment grades to the gradebook.
    This ensures that all graded assignments have corresponding
    Grade records in the gradebook.
    """
    try:
        logger.info("Starting scheduled gradebook sync...")
        call_command('sync_gradebook')
        logger.info("Scheduled gradebook sync completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error during scheduled gradebook sync: {str(e)}")
        return False 