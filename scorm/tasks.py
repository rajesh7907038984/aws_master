"""
SCORM Background Tasks
Continuous monitoring and automatic fixing of SCORM score issues
"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .real_time_validator import ScormScoreValidator
from .dynamic_score_processor import auto_process_scorm_score
from .models import ScormAttempt

logger = logging.getLogger(__name__)


@shared_task
def continuous_scorm_monitoring():
    """
    Background task that continuously monitors and fixes SCORM score issues
    Should be run every 15 minutes via cron or Celery beat
    """
    logger.info("🔄 Starting continuous SCORM monitoring...")
    
    try:
        # Validate recent attempts (last 30 minutes)
        results = ScormScoreValidator.validate_recent_attempts(hours=0.5)
        
        logger.info(f"Continuous Monitor: Checked {results['checked']} attempts, "
                   f"found {results['issues']} issues, applied {results['fixes']} fixes")
        
        # If many issues found, run broader validation
        if results['issues'] > 5:
            logger.warning("High number of SCORM issues detected - running broader validation")
            broader_results = ScormScoreValidator.validate_recent_attempts(hours=4)
            logger.info(f"Broader validation: {broader_results}")
        
        return {
            'status': 'success',
            'timestamp': timezone.now().isoformat(),
            'results': results
        }
        
    except Exception as e:
        logger.error(f"Continuous Monitor: Error during monitoring: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def auto_process_stuck_attempts():
    """
    Find and process SCORM attempts that are "stuck" - have data but no completion
    """
    logger.info("🔄 Processing stuck SCORM attempts...")
    
    try:
        # Find attempts that have been accessed recently but have no score despite having suspend data
        since = timezone.now() - timedelta(hours=24)
        
        stuck_attempts = ScormAttempt.objects.filter(
            last_accessed__gte=since,
            score_raw__isnull=True,
            suspend_data__isnull=False,
            lesson_status__in=['not_attempted', 'incomplete']
        ).exclude(
            suspend_data=''
        ).filter(
            # Only process attempts with substantial suspend data (likely has real progress)
            suspend_data__regex=r'.{100,}'  # At least 100 characters
        )
        
        processed = 0
        fixed = 0
        
        for attempt in stuck_attempts:
            processed += 1
            
            logger.info(f"Processing stuck attempt {attempt.id} for user {attempt.user.username}")
            
            if auto_process_scorm_score(attempt):
                fixed += 1
                logger.info(f"Fixed stuck attempt {attempt.id}")
            
            # Rate limiting - process max 20 attempts per run
            if processed >= 20:
                break
        
        logger.info(f"Stuck Attempts Processor: Processed {processed}, fixed {fixed}")
        
        return {
            'status': 'success',
            'processed': processed,
            'fixed': fixed,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Stuck Attempts Processor: Error: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task  
def validate_gradebook_data(course_id):
    """
    Validate SCORM scores for a specific course before gradebook display
    Ensures accurate data is shown to users
    """
    try:
        logger.info(f"Validating gradebook data for course {course_id}")
        
        from courses.models import CourseTopic
        from .models import ScormAttempt
        
        # Get all SCORM topics in this course
        course_topics = CourseTopic.objects.filter(
            course_id=course_id,
            topic__scorm_package__isnull=False
        ).select_related('topic__scorm_package')
        
        validated = 0
        fixed = 0
        
        for course_topic in course_topics:
            topic = course_topic.topic
            
            # Get recent attempts for this topic
            recent_attempts = ScormAttempt.objects.filter(
                scorm_package__topic=topic,
                last_accessed__gte=timezone.now() - timedelta(hours=48)
            )
            
            for attempt in recent_attempts:
                is_valid, was_fixed, details = ScormScoreValidator.validate_and_sync_attempt(attempt.id)
                validated += 1
                
                if was_fixed:
                    fixed += 1
        
        logger.info(f"Gradebook Validation: Course {course_id} - validated {validated}, fixed {fixed}")
        
        return {
            'status': 'success',
            'course_id': course_id,
            'validated': validated,
            'fixed': fixed,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Gradebook Validation: Error for course {course_id}: {str(e)}")
        return {
            'status': 'error',
            'course_id': course_id,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }
