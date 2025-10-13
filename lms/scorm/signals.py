"""
SCORM Signals - Dynamic Score Processing
Automatically detects and processes SCORM scores using adaptive patterns
Works for all SCORM authoring tools and formats - fully dynamic
"""
import logging
import re
import json
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from django.utils import timezone
from .dynamic_score_processor import auto_process_scorm_score

logger = logging.getLogger(__name__)


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
                passing_score = 70.0  # Default passing score
            
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
    """Extract score from decoded suspend data - ONLY extract actual earned scores, not configuration values"""
    try:
        # CRITICAL FIX: Be much more selective about score extraction
        # Don't extract scores unless there's clear evidence of actual completion/interaction
        
        # Check for evidence of actual progress/completion first
        has_completion_evidence = (
            'complete' in decoded_data.lower() or
            'finished' in decoded_data.lower() or
            'done' in decoded_data.lower() or
            '"qd"true' in decoded_data or  # Quiz done = true (format 1)
            'qd":true' in decoded_data or  # Quiz done = true (format 2)  
            'qd"true' in decoded_data or   # Quiz done = true (format 3)
            'quiz_complete' in decoded_data.lower() or
            'assessment_complete' in decoded_data.lower() or
            'lesson_complete' in decoded_data.lower()
        )
        
        if not has_completion_evidence:
            logger.info("No completion evidence found in suspend data - not extracting score to prevent false completion")
            return None
        
        # Pattern 1: Look for explicit score with completion context
        # Only extract if there's clear completion context
        completion_score_pattern = re.search(r'(?:quiz_score|final_score|earned_score|user_score)"\s*:\s*(\d+\.?\d*)', decoded_data, re.IGNORECASE)
        if completion_score_pattern:
            score = float(completion_score_pattern.group(1))
            if 0 <= score <= 100:
                logger.info(f"Found explicit completion score: {score}")
                return score
        
        # Pattern 2: Storyline pattern but ONLY if quiz is marked as done
        if '"qd"true' in decoded_data or 'quiz_done":true' in decoded_data or '"qd":true' in decoded_data or 'qd"true' in decoded_data:
            logger.info("Quiz marked as done - looking for actual earned score")
            
            # Pattern 2a: Look for score in various Storyline formats WITH BETTER FILTERING
            # Avoid patterns that might be configuration values
            # Look specifically for patterns that indicate actual earned scores
            
            # Check for actual score indicators (not config values)
            # Example: "scors100" (actual score) vs "ps80" (passing score config)
            scor_patterns = [
                r'(?<!p)scors(\d+)',           # scors88 but not pscors88
                r'(?<!p)scor["\s]*(\d+)',      # scor"88 but not pscor
                r'actual_score["\s:]*(\d+)',   # actual_score patterns
                r'earned_score["\s:]*(\d+)',   # earned_score patterns
            ]
            
            for pattern in scor_patterns:
                scor_match = re.search(pattern, decoded_data)
                if scor_match:
                    score = float(scor_match.group(1))
                    # Additional validation: avoid common config values
                    if score not in [6, 60, 70, 75, 80, 85, 90, 95] or score == 100:  # 100 is likely a real perfect score
                        if 0 <= score <= 100:
                            logger.info(f"Found Storyline quiz score (pattern: {pattern}): {score}")
                            return score
            
            # Pattern 2b: Look for actual user score patterns in completed quiz
            storyline_pattern = re.search(r'(?:user_score|earned|result)"\s*:\s*(\d+)', decoded_data, re.IGNORECASE)
            if storyline_pattern:
                score = float(storyline_pattern.group(1))
                if 0 <= score <= 100:
                    logger.info(f"Found Storyline completed quiz score: {score}")
                    return score
        
        # Pattern 3: Look for score with completion percentage
        if 'progress' in decoded_data and ('100' in decoded_data or 'complete' in decoded_data.lower()):
            # Only look for actual user scores, avoid configuration values
            user_score_pattern = re.search(r'(?:user_score|final_result|earned_points)"\s*:\s*(\d+\.?\d*)', decoded_data, re.IGNORECASE)
            if user_score_pattern:
                score = float(user_score_pattern.group(1))
                if 0 <= score <= 100:
                    logger.info(f"Found progress-based completion score: {score}")
                    return score
        
        # REMOVED: The problematic patterns that were extracting configuration values
        # - No longer extract standalone "s80" values (these are often thresholds)
        # - No longer extract generic percentage values without completion context
        # - No longer extract "score":value without clear completion evidence
        
        logger.info("No valid earned score found in suspend data (found possible threshold/config values but no completion evidence)")
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
            # Default to 70% if no mastery score is defined
            passing_score = 70.0
        
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

