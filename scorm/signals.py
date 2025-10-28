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
def auto_fix_storyline_completion(sender, instance, created, **kwargs):
    """
    AUTOMATIC FIX: Detect and fix Storyline completion issues on attempt save
    This runs after every SCORM attempt save to catch completion issues
    """
    # Skip if this is being processed by other signals
    if hasattr(instance, '_signal_processing'):
        return
    
    try:
        # Only process attempts with suspend data
        if not instance.suspend_data or len(instance.suspend_data) < 10:
            return
        
        # Only process incomplete attempts
        if instance.lesson_status != 'incomplete':
            return
        
        # Check if this looks like a Storyline package
        is_storyline = (
            hasattr(instance.scorm_package, 'version') and 
            instance.scorm_package.version == 'storyline'
        ) or 'storyline' in (instance.scorm_package.package_file.name or '').lower()
        
        if not is_storyline:
            return
        
        logger.info(f"AUTO_FIX: Checking Storyline attempt {instance.id} for completion")
        
        # Import the fixer
        from .storyline_completion_fixer import StorylineCompletionFixer
        
        fixer = StorylineCompletionFixer()
        success, reason = fixer.fix_attempt(instance)
        
        if success:
            logger.info(f"AUTO_FIX: ✅ Fixed attempt {instance.id} - {reason}")
        else:
            logger.debug(f"AUTO_FIX: ⏭️  Skipped attempt {instance.id} - {reason}")
            
    except Exception as e:
        logger.error(f"AUTO_FIX ERROR: Failed to process attempt {instance.id}: {str(e)}")


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
    """Decode compressed suspend_data from Storyline format with enhanced error handling"""
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
                    if chars[i] - 256 < len(decoded):
                        decoded += decoded[chars[i] - 256]
                    else:
                        # Handle out of bounds reference
                        decoded += '?'
                else:
                    # New character
                    decoded += chr(chars[i])
                i += 1
            
            return decoded
        
        # Already decoded or different format
        return str(data)
        
    except Exception as e:
        logger.debug(f"Could not decode suspend_data: {e}")
        # ENHANCED: Try to extract useful information even from corrupted data
        try:
            # Look for completion keywords in raw data
            raw_lower = suspend_data.lower()
            if any(keyword in raw_lower for keyword in ['qd', 'complete', 'done', 'finished']):
                logger.info("Found completion keywords in raw suspend data")
                return suspend_data  # Return raw data for pattern matching
        except:
            pass
        return None


def _extract_score_from_data(decoded_data):
    """Extract score using proper SCORM CMI data - NO CUSTOM CALCULATIONS"""
    try:
        # PRIMARY: Look for CMI score data first
        cmi_score_patterns = [
            r'cmi\.core\.score\.raw["\s:]*(\d+(?:\.\d+)?)',  # SCORM 1.2 score
            r'cmi\.score\.raw["\s:]*(\d+(?:\.\d+)?)',        # SCORM 2004 score
            r'cmi\.core\.score\.scaled["\s:]*(\d+(?:\.\d+)?)', # SCORM 1.2 scaled
            r'cmi\.score\.scaled["\s:]*(\d+(?:\.\d+)?)',     # SCORM 2004 scaled
        ]
        
        for pattern in cmi_score_patterns:
            score_match = re.search(pattern, decoded_data, re.IGNORECASE)
            if score_match:
                score = float(score_match.group(1))
                if 0 <= score <= 100:
                    logger.info(f"SCORM CMI: Found CMI score {score}% using pattern {pattern}")
                    return score
        
        # SECONDARY: Look for CMI completion status for pass/fail
        cmi_completion_patterns = [
            r'cmi\.completion_status["\s:]*["\']?(completed|passed|failed)["\']?',
            r'cmi\.core\.lesson_status["\s:]*["\']?(completed|passed|failed)["\']?',
            r'cmi\.success_status["\s:]*["\']?(passed|failed)["\']?',
        ]
        
        for pattern in cmi_completion_patterns:
            status_match = re.search(pattern, decoded_data, re.IGNORECASE)
            if status_match:
                status = status_match.group(1).lower()
                if status in ['completed', 'passed']:
                    logger.info(f"SCORM CMI: Found completion status '{status}' - scoring as 100%")
                    return 100.0
                elif status == 'failed':
                    logger.info(f"SCORM CMI: Found completion status '{status}' - scoring as 0%")
                    return 0.0
        
        # TERTIARY: Look for actual quiz scores (not calculated)
        actual_score_patterns = [
            r'scors(\d+)',                    # Storyline: scors88
            r'scor["\s]*(\d+)',              # Storyline: scor"88 
            r'quiz_score["\s:]*(\d+)',       # quiz_score:88
            r'final_score["\s:]*(\d+)',      # final_score:88
            r'user_score["\s:]*(\d+)',       # user_score:88
        ]
        
        for pattern in actual_score_patterns:
            score_match = re.search(pattern, decoded_data, re.IGNORECASE)
            if score_match:
                score = float(score_match.group(1))
                if 0 <= score <= 100:
                    logger.info(f"SCORM CMI: Found actual quiz score {score}% using pattern {pattern}")
                    return score
        
        # NO CUSTOM CALCULATIONS - Only use SCORM CMI data
        logger.info(f"SCORM CMI: No valid CMI data found for score extraction")
        return None
        
    except Exception as e:
        logger.error(f"SCORM CMI: Error extracting score: {str(e)}")
        return None


def _update_topic_progress(attempt, score_value):
    """Update TopicProgress with package-type-specific validation"""
    try:
        from courses.models import TopicProgress
        
        topic = attempt.scorm_package.topic
        
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=attempt.user,
            topic=topic
        )
        
        # DIFFERENT COMPLETION VALIDATION BASED ON PACKAGE TYPE
        package = attempt.scorm_package
        
        if package.is_quiz_based():
            # QUIZ-BASED: Use standard SCORM completion logic
            is_completed = (
                attempt.lesson_status in ['passed', 'failed', 'completed'] or
                attempt.completion_status in ['completed', 'passed'] or
                attempt.success_status in ['passed'] or
                (attempt.score_raw is not None and attempt.score_raw >= (package.mastery_score or 70))
            )
            
        elif package.is_slide_based():
            # SLIDE-BASED: Use ONLY CMI completion status (proper SCORM standard)
            is_completed = (
                # PRIMARY: Trust CMI completion status (proper SCORM standard)
                attempt.completion_status in ['completed', 'passed'] or
                attempt.lesson_status in ['completed', 'passed'] or
                attempt.success_status in ['passed'] or
                
                # CMI DATA VALIDATION: Check CMI data fields
                attempt.cmi_data.get('cmi.completion_status') in ['completed', 'passed'] or
                attempt.cmi_data.get('cmi.core.lesson_status') in ['completed', 'passed'] or
                attempt.cmi_data.get('cmi.success_status') in ['passed'] or
                
                # BACKUP: Score-based completion (only if valid score exists)
                (attempt.score_raw is not None and attempt.score_raw >= (package.mastery_score or 70))
            )
            
        else:
            # UNKNOWN TYPE: Use conservative approach
            is_completed = (
                attempt.lesson_status in ['passed', 'failed', 'completed'] or
                attempt.completion_status in ['completed', 'passed'] or
                attempt.success_status in ['passed'] or
                (attempt.score_raw is not None and attempt.score_raw >= (package.mastery_score or 70))
            )
        
        if not is_completed:
            logger.info(f"📊 SCORM: Not completed yet (status: {attempt.lesson_status}, type: {package.get_package_type()}) - skipping TopicProgress update")
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
        
        logger.info(f"✅ SCORM: Updated topic {topic.id} for user {attempt.user.username} - Score: {score_value}, Type: {package.get_package_type()}")
        
    except Exception as e:
        logger.error(f"Error updating TopicProgress: {str(e)}")


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

