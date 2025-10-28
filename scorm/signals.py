"""
SCORM Signals - CMI Data Only
Uses only standard SCORM CMI data for tracking and scoring
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


@receiver(post_save, sender='scorm.ScormAttempt')
def cmi_score_processor(sender, instance, created, **kwargs):
    """
    Process SCORM scores using only CMI data
    """
    if created:
        return
    
    # Skip if this save was triggered by the API handler
    if getattr(instance, '_updating_from_api_handler', False):
        return
    
    try:
        # Use centralized sync service with CMI data only
        from .score_sync_service import ScormScoreSyncService
        success = ScormScoreSyncService.sync_score(instance)
        
        if success:
            logger.info(f"✅ CMI: Successfully synchronized score for attempt {instance.id}")
        
    except Exception as e:
        logger.error(f"❌ CMI: Error synchronizing attempt {instance.id}: {str(e)}")


def _extract_score_from_cmi_data(attempt):
    """Extract score using only CMI data - no custom calculations"""
    try:
        scores = []
        
        # Priority 1: Direct score_raw field
        if attempt.score_raw is not None:
            scores.append(float(attempt.score_raw))
        
        # Priority 2: CMI data scores
        if attempt.cmi_data:
            # SCORM 2004
            cmi_score = attempt.cmi_data.get('cmi.score.raw')
            if cmi_score is not None:
                try:
                    scores.append(float(cmi_score))
                except:
                    pass
            
            # SCORM 1.2
            core_score = attempt.cmi_data.get('cmi.core.score.raw')
            if core_score is not None:
                try:
                    scores.append(float(core_score))
                except:
                    pass
            
            # Scaled score (convert from 0-1 to 0-100)
            scaled_score = attempt.cmi_data.get('cmi.score.scaled') or attempt.cmi_data.get('cmi.core.score.scaled')
            if scaled_score is not None:
                try:
                    scores.append(float(scaled_score) * 100)
                except:
                    pass
        
        # Return the highest score found
        return max(scores) if scores else None
        
    except Exception as e:
        logger.error(f"CMI: Error extracting score: {str(e)}")
        return None


def _update_topic_progress_cmi_only(attempt, score_value):
    """Update TopicProgress using only CMI completion status"""
    try:
        from courses.models import TopicProgress
        
        topic = attempt.scorm_package.topic
        
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=attempt.user,
            topic=topic
        )
        
        # Use only CMI completion status (proper SCORM standard)
        is_completed = (
            # PRIMARY: Trust CMI completion status (proper SCORM standard)
            attempt.completion_status in ['completed', 'passed'] or
            attempt.lesson_status in ['completed', 'passed'] or
            attempt.success_status in ['passed'] or
            
            # CMI DATA VALIDATION: Check CMI data fields
            attempt.cmi_data.get('cmi.completion_status') in ['completed', 'passed'] or
            attempt.cmi_data.get('cmi.core.lesson_status') in ['completed', 'passed'] or
            attempt.cmi_data.get('cmi.success_status') in ['passed']
        )
        
        if not is_completed:
            logger.info(f"📊 CMI: Not completed yet (status: {attempt.lesson_status}) - skipping TopicProgress update")
            return
        
        # Only update if SCORM explicitly indicates completion
        topic_progress.last_score = float(score_value)
        
        # Update best score
        if topic_progress.best_score is None or score_value > float(topic_progress.best_score):
            topic_progress.best_score = float(score_value)
        
        # Mark as completed only if SCORM says so
        if not topic_progress.completed:
            topic_progress.completed = True
            topic_progress.completion_method = 'scorm'
            topic_progress.completed_at = timezone.now()
        
        topic_progress.save()
        
        logger.info(f"✅ CMI: Updated topic {topic.id} for user {attempt.user.username} - Score: {score_value}")
        
    except Exception as e:
        logger.error(f"Error updating TopicProgress: {str(e)}")

