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
            'lesson_complete' in decoded_data.lower() or
            # STORYLINE FIX: Add more Storyline completion patterns
            'qd"true' in decoded_data or
            'qd":true' in decoded_data or
            'quiz_done":true' in decoded_data or
            'assessment_done":true' in decoded_data or
            'lesson_done":true' in decoded_data
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
                # STORYLINE FIX: Add more comprehensive Storyline score patterns
                r'scors(\d+)',                 # Direct scors pattern
                r'scor["\s]*(\d+)',            # Direct scor pattern
                r'quiz_score["\s:]*(\d+)',     # quiz_score patterns
                r'final_score["\s:]*(\d+)',    # final_score patterns
                r'user_score["\s:]*(\d+)',     # user_score patterns
                r'earned["\s:]*(\d+)',         # earned patterns
                r'result["\s:]*(\d+)',        # result patterns
            ]
            
            for pattern in scor_patterns:
                scor_match = re.search(pattern, decoded_data)
                if scor_match:
                    score = float(scor_match.group(1))
                    # STORYLINE FIX: More lenient validation for Storyline scores
                    # Accept any valid score between 0-100, including common values
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
        
        # STORYLINE FIX: Handle case where quiz is complete but score field is empty
        # This happens when score is 100% in some SCORM packages (especially Articulate Storyline)
        if has_completion_evidence and _is_score_field_empty(decoded_data):
            logger.info("Storyline quiz complete with empty score field - assuming 100% score")
            return 100.0
        
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
    """Update TopicProgress with extracted score - Only when SCORM is completed"""
    try:
        from courses.models import TopicProgress
        
        topic = attempt.scorm_package.topic
        
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=attempt.user,
            topic=topic
        )
        
        # CRITICAL FIX: Only update scores when SCORM is completed
        # Check completion status
        is_completed = attempt.lesson_status in ['passed', 'failed', 'completed']
        
        if not is_completed:
            logger.info(f"📊 AUTO-EXTRACT: SCORM not completed yet (status: {attempt.lesson_status}) - skipping TopicProgress score update")
            return
        
        # Update last score
        old_last = topic_progress.last_score
        old_best = topic_progress.best_score
        
        topic_progress.last_score = float(score_value)
        
        # Update best score if this is better
        if not topic_progress.best_score or float(score_value) > topic_progress.best_score:
            topic_progress.best_score = float(score_value)
        
        # Mark as completed
        if not topic_progress.completed:
            topic_progress.completed = True
            topic_progress.completion_method = 'scorm'
            topic_progress.completed_at = timezone.now()
        
        topic_progress.save()
        
        logger.info(f"📊 AUTO-EXTRACT: SCORM completed - Updated TopicProgress - last_score: {old_last} → {topic_progress.last_score}, best_score: {old_best} → {topic_progress.best_score}")
        
    except Exception as e:
        logger.error(f"Error updating TopicProgress: {e}")


def _is_score_field_empty(decoded_data):
    """
    Check if the score field exists but is empty
    This is a specific issue with some SCORM packages when score is 100%
    """
    try:
        # Check for empty score patterns
        empty_patterns = [
            r'scors"[\s]*[,}]',      # scors" followed by comma or closing brace
            r'scor"[\s]*[,}]',       # scor" followed by comma or closing brace
            r'"score"[\s]*:[\s]*""',  # "score": ""
            r'"score"[\s]*:[\s]*[,}]', # "score": followed by comma or closing brace
            r'quiz_score"[\s]*:[\s]*""', # "quiz_score": ""
            r'user_score"[\s]*:[\s]*""', # "user_score": ""
        ]
        
        for pattern in empty_patterns:
            if re.search(pattern, decoded_data, re.IGNORECASE):
                logger.info(f"Found empty score field with pattern: {pattern}")
                return True
        
        # Additional check for Storyline specific format
        # Look for 'scor"' at the end of the string or followed by }
        if 'scor"' in decoded_data:
            pos = decoded_data.find('scor"')
            # Check what comes after 'scor"'
            next_chars = decoded_data[pos+5:pos+6] if pos+5 < len(decoded_data) else ''
            if not next_chars or next_chars in ['}', ',', ']', ' ']:
                logger.info(f"Found empty score field (scor\" with no value)")
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking for empty score field: {str(e)}")
        return False

