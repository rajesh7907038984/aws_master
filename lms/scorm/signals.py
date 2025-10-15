"""
SCORM Signals - Simplified Score Processing
Basic SCORM score synchronization following global standards
"""
import logging
import re
import json
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_dynamic_passing_score(scorm_package):
    """
    Get dynamic passing score based on SCORM package type and course settings
    Replaces hardcoded 70% with intelligent defaults
    """
    try:
        # Check if course has specific completion requirements
        topic = scorm_package.topic
        if hasattr(topic, 'course') and topic.course:
            course = topic.course
            # Use course completion percentage as base, but adjust for SCORM
            if hasattr(course, 'completion_percentage') and course.completion_percentage:
                # Convert course completion percentage to passing score
                # If course requires 80% completion, use 80% as passing score
                return float(course.completion_percentage)
        
        # Check SCORM package type for intelligent defaults
        version = scorm_package.version
        if version in ['2004', 'xapi']:
            # SCORM 2004 and xAPI typically use higher standards
            return 80.0
        elif version in ['storyline', 'captivate', 'lectora']:
            # Authoring tools often have different standards
            return 75.0
        elif version in ['1.1', '1.2']:
            # Traditional SCORM versions
            return 70.0
        else:
            # Default fallback
            return 70.0
            
    except Exception as e:
        logger.warning(f"Error getting dynamic passing score: {e}")
        # Safe fallback
        return 70.0


@receiver(post_save, sender='scorm.ScormAttempt')
def dynamic_score_processor(sender, instance, created, **kwargs):
    """
    DYNAMIC SCORE PROCESSOR - Automatically handles all SCORM formats
    Uses centralized ScormScoreSyncService for consistent score synchronization
    Enhanced with auto-completion logic when passmark is achieved
    """
    # Import the sync service
    from .score_sync_service import ScormScoreSyncService
    
    # Skip if this is a new attempt creation
    if created:
        return
    
    # Skip if this save was triggered by the API handler or another signal
    if (getattr(instance, '_updating_from_api_handler', False) or
        getattr(instance, '_updating_from_signal', False) or
        getattr(instance, '_signal_processing', False)):
        logger.info(f"🔄 SYNC: Skipping signal for attempt {instance.id} - update in progress by another component")
        return
    
    try:
        # Use a flag to prevent recursive signal calls
        instance._signal_processing = True
        
        logger.info(f"🔄 SYNC: Processing score synchronization for attempt {instance.id}...")
        
        # Use the centralized sync service
        success = ScormScoreSyncService.sync_score(instance)
        
        if success:
            logger.info(f"✅ SYNC: Successfully synchronized score for attempt {instance.id}")
        else:
            logger.info(f"ℹ️  SYNC: No score synchronization needed for attempt {instance.id}")
        
        # ENHANCED AUTO-COMPLETION CHECK
        # Check if we should trigger auto-completion based on score
        if instance.score_raw is not None and instance.score_raw > 0:
            # Check if learner has achieved passing score
            mastery_score = instance.scorm_package.mastery_score
            if mastery_score is not None:
                passing_score = float(mastery_score)
            else:
                # Dynamic default based on SCORM package type and course settings
                passing_score = _get_dynamic_passing_score(instance.scorm_package)
            
            has_passed = float(instance.score_raw) >= passing_score
            scorm_completed = instance.lesson_status in ['passed', 'failed', 'completed']
            
            # Trigger auto-completion if learner achieved passing score
            if has_passed and not scorm_completed:
                logger.info(f"🎯 AUTO-COMPLETION: Learner achieved passing score {instance.score_raw}% (required: {passing_score}%) - triggering auto-completion")
                
                # Update SCORM attempt status to reflect completion
                instance.lesson_status = 'passed'
                instance.completion_status = 'completed'
                instance.success_status = 'passed'
                instance.save(update_fields=['lesson_status', 'completion_status', 'success_status'])
                
                # Trigger topic progress update
                _update_topic_progress(instance, instance.score_raw)
                
            elif scorm_completed:
                # SCORM already reported completion, just update topic progress
                _update_topic_progress(instance, instance.score_raw)
        
    except Exception as e:
        logger.error(f"❌ SYNC: Error synchronizing attempt {instance.id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # Clean up the flag
        if hasattr(instance, '_signal_processing'):
            delattr(instance, '_signal_processing')


def _decode_suspend_data(suspend_data):
    """Decode compressed suspend_data from Storyline format"""
    try:
        data = json.loads(suspend_data)
        
        # Check if it's compressed format
        if 'v' in data and 'd' in data:
            chars = data['d']
            decoded = ''
            i = 0
            
            while i < len(chars):
                if chars[i] > 255:
                    # Reference to previous character
                    decoded += decoded[chars[i] - 256]
                else:
                    # New character
                    decoded += chr(chars[i])
                i += 1
            
            return decoded
        
        # Already decoded or different format
        return str(data)
        
    except Exception as e:
        logger.debug(f"Could not decode suspend_data: {e}")
        return None


def _extract_score_from_data(decoded_data):
    """Extract score from decoded suspend data - simplified approach"""
    try:
        # Check for clear completion indicators
        completion_indicators = ['complete', 'finished', 'done', '"qd"true', 'quiz_complete']
        has_completion = any(indicator in decoded_data.lower() for indicator in completion_indicators)
        
        if not has_completion:
            logger.debug("No completion evidence found in suspend data")
            return None
        
        # Look for explicit score patterns
        score_patterns = [
            r'(?:quiz_score|final_score|earned_score|user_score)"\s*:\s*(\d+\.?\d*)',
            r'scors(\d+)',  # Storyline format
            r'(?:user_score|earned|result)"\s*:\s*(\d+)'
        ]
        
        for pattern in score_patterns:
            match = re.search(pattern, decoded_data, re.IGNORECASE)
            if match:
                score = float(match.group(1))
                if 0 <= score <= 100:
                    logger.info(f"Found completion score: {score}")
                    return score
        
        logger.debug("No valid score found in suspend data")
        return None
        
    except Exception as e:
        logger.debug(f"Could not extract score: {e}")
        return None


def _update_topic_progress(attempt, score_value):
    """Update TopicProgress with extracted score - Auto-completion when passmark is achieved"""
    try:
        from courses.models import TopicProgress
        
        topic = attempt.scorm_package.topic
        
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=attempt.user,
            topic=topic
        )
        
        # Update scores regardless of completion status
        old_last = topic_progress.last_score
        old_best = topic_progress.best_score
        
        topic_progress.last_score = float(score_value)
        
        # Update best score if this is better
        if not topic_progress.best_score or float(score_value) > topic_progress.best_score:
            topic_progress.best_score = float(score_value)
        
        # ENHANCED AUTO-COMPLETION LOGIC
        # Check if learner has achieved passing score based on mastery score
        mastery_score = attempt.scorm_package.mastery_score
        if mastery_score is not None:
            # Use the defined mastery score from SCORM package
            passing_score = float(mastery_score)
        else:
            # Dynamic default based on SCORM package type and course settings
            passing_score = _get_dynamic_passing_score(attempt.scorm_package)
        
        # Check if current score meets or exceeds the passing requirement
        has_passed = float(score_value) >= passing_score
        
        # Check completion status from SCORM
        scorm_completed = attempt.lesson_status in ['passed', 'failed', 'completed']
        
        # Auto-complete if either SCORM reports completion OR learner achieved passing score
        should_complete = scorm_completed or has_passed
        
        if should_complete and not topic_progress.completed:
            topic_progress.completed = True
            topic_progress.completion_method = 'scorm'
            topic_progress.completed_at = timezone.now()
            
            # Log the completion reason
            if scorm_completed:
                logger.info(f"📊 AUTO-COMPLETE: SCORM reported completion (status: {attempt.lesson_status}) - TopicProgress marked as completed")
            elif has_passed:
                logger.info(f"📊 AUTO-COMPLETE: Learner achieved passing score {score_value}% (required: {passing_score}%) - TopicProgress marked as completed")
        
        topic_progress.save()
        
        if should_complete:
            logger.info(f"📊 AUTO-EXTRACT: SCORM completed - Updated TopicProgress - last_score: {old_last} → {topic_progress.last_score}, best_score: {old_best} → {topic_progress.best_score}")
        else:
            logger.info(f"📊 AUTO-EXTRACT: Score updated but not yet passing - last_score: {old_last} → {topic_progress.last_score}, best_score: {old_best} → {topic_progress.best_score} (required: {passing_score}%)")
        
    except Exception as e:
        logger.error(f"Error updating TopicProgress: {e}")

