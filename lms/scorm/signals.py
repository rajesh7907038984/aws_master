"""
SCORM Signals - Simplified Score Processing
Basic SCORM score synchronization
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


@receiver(post_save, sender='scorm.ScormAttempt')
def simple_score_processor(sender, instance, created, **kwargs):
    """
    Simple score processor for SCORM attempts
    """
    # Skip if this is a new attempt creation
    if created:
        return
    
    # Skip if this save was triggered by another signal
    if getattr(instance, '_signal_processing', False):
        return
    
    try:
        # Use a flag to prevent recursive signal calls
        instance._signal_processing = True
        
        logger.info(f"Processing score for attempt {instance.id}")
        
        # Update topic progress if score is available
        if instance.score_raw is not None and instance.score_raw > 0:
            _update_topic_progress(instance, float(instance.score_raw))
        
    except Exception as e:
        logger.error(f"Error processing attempt {instance.id}: {str(e)}")
    finally:
        # Clean up the flag
        if hasattr(instance, '_signal_processing'):
            delattr(instance, '_signal_processing')


def _update_topic_progress(attempt, score_value):
    """Update TopicProgress with score"""
    try:
        from courses.models import TopicProgress
        
        topic = attempt.scorm_package.topic
        
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=attempt.user,
            topic=topic
        )
        
        # Update scores
        topic_progress.last_score = float(score_value)
        
        # Update best score if this is better
        if not topic_progress.best_score or float(score_value) > topic_progress.best_score:
            topic_progress.best_score = float(score_value)
        
        # Check if SCORM reports completion
        if attempt.lesson_status in ['passed', 'completed']:
            topic_progress.completed = True
            topic_progress.completion_method = 'scorm'
            topic_progress.completed_at = timezone.now()
            logger.info(f"SCORM completed - TopicProgress marked as completed")
        
        topic_progress.save()
        logger.info(f"Updated TopicProgress - score: {score_value}")
        
    except Exception as e:
        logger.error(f"Error updating TopicProgress: {e}")