"""
SCORM Celery Tasks
Background tasks for processing SCORM packages
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def process_scorm_package(package_id):
    """
    Process a SCORM package asynchronously
    Extracts ZIP, parses manifest, uploads to S3
    """
    try:
        from .models import SCORMPackage
        from .views import SCORMPackageUploadView
        
        package = SCORMPackage.objects.get(id=package_id)
        
        # Create a view instance to use its processing method
        view = SCORMPackageUploadView()
        success = view.process_package(package)
        
        if success:
            logger.info(f"Successfully processed SCORM package: {package.title}")
            return {
                'status': 'success',
                'package_id': str(package_id),
                'title': package.title
            }
        else:
            logger.error(f"Failed to process SCORM package: {package.title}")
            return {
                'status': 'error',
                'package_id': str(package_id),
                'error': package.processing_error
            }
    
    except Exception as e:
        logger.error(f"Error in process_scorm_package task: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'package_id': str(package_id),
            'error': str(e)
        }


@shared_task
def cleanup_old_scorm_attempts(days=90):
    """
    Clean up old SCORM attempts and events
    """
    from datetime import timedelta
    from django.utils import timezone
    from .models import SCORMAttempt, SCORMEvent
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Delete old events
    deleted_events = SCORMEvent.objects.filter(
        timestamp__lt=cutoff_date
    ).delete()
    
    logger.info(f"Deleted {deleted_events[0]} old SCORM events")
    
    return {
        'status': 'success',
        'deleted_events': deleted_events[0]
    }

