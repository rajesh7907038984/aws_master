"""
SCORM Signals - Automatic Score Extraction
Automatically extracts scores from suspend_data when SCORM attempts are saved
Works WITHOUT any user interaction - runs in background
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


@receiver(post_save, sender='scorm.ScormAttempt')
def auto_extract_score_on_save(sender, instance, created, **kwargs):
    """
    AUTOMATIC SCORE EXTRACTION - Fallback only when API handler doesn't work
    Extracts score from suspend_data as a last resort
    Coordinates with the main API handler to prevent race conditions
    """
    # Skip if this is a new attempt creation
    if created:
        return
    
    # Skip if score is already set and looks correct
    if instance.score_raw and instance.score_raw > 0:
        return
    
    # Skip if no suspend_data
    if not instance.suspend_data:
        return
    
    # Skip if this save was triggered by the enhanced API handler
    # (check if this is part of a transaction from the API handler)
    if getattr(instance, '_updating_from_api_handler', False):
        logger.info(f"🤖 AUTO-EXTRACT: Skipping signal for attempt {instance.id} - API handler is managing the update")
        return
    
    try:
        # Use a flag to prevent recursive signal calls
        if hasattr(instance, '_signal_processing'):
            return
        instance._signal_processing = True
        
        logger.info(f"🤖 AUTO-EXTRACT: Checking attempt {instance.id} for unreported scores (fallback mode)...")
        
        # Decode and decompress suspend_data
        decoded_data = _decode_suspend_data(instance.suspend_data)
        
        if not decoded_data:
            return
        
        # Extract score from decoded data
        extracted_score = _extract_score_from_data(decoded_data)
        
        if extracted_score and extracted_score > 0:
            logger.info(f"✅ AUTO-EXTRACT: Found score {extracted_score} in suspend_data for attempt {instance.id} (fallback extraction)")
            
            # Use atomic transaction to prevent race conditions
            from django.db import transaction
            
            with transaction.atomic():
                # Re-fetch the instance with select_for_update to prevent race conditions
                updated_instance = sender.objects.select_for_update().get(id=instance.id)
                
                # Double-check that score is still not set (another process might have set it)
                if updated_instance.score_raw and updated_instance.score_raw > 0:
                    logger.info(f"ℹ️  AUTO-EXTRACT: Score already set by another process for attempt {instance.id}")
                    return
                
                # Update the score
                updated_instance.score_raw = Decimal(str(extracted_score))
                
                # Set status based on score
                mastery_score = updated_instance.scorm_package.mastery_score or 80
                if extracted_score >= mastery_score:
                    updated_instance.lesson_status = 'passed'
                else:
                    updated_instance.lesson_status = 'failed'
                
                # Mark that this is being updated by signal to prevent recursion
                updated_instance._updating_from_signal = True
                
                # Save without triggering this signal again
                updated_instance.save(update_fields=['score_raw', 'lesson_status'])
                
                # CRITICAL FIX: Only update TopicProgress if SCORM is completed
                # Check if lesson_status indicates completion
                if updated_instance.lesson_status in ['passed', 'failed', 'completed']:
                    # Update TopicProgress within the same transaction
                    _update_topic_progress(updated_instance, extracted_score)
                    logger.info(f"✅ AUTO-EXTRACT: SCORM completed - updated TopicProgress with score")
                else:
                    logger.info(f"ℹ️  AUTO-EXTRACT: SCORM in progress (status: {updated_instance.lesson_status}) - not updating TopicProgress yet")
                
                logger.info(f"✅ AUTO-EXTRACT: Successfully updated score to {extracted_score} for attempt {instance.id}")
            
            # Clear relevant caches
            cache.delete_many([
                f'scorm_attempt_{instance.id}',
                f'topic_progress_{instance.user.id}_{instance.scorm_package.topic.id}',
            ])
        
    except Exception as e:
        logger.error(f"❌ AUTO-EXTRACT: Error extracting score for attempt {instance.id}: {str(e)}")
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
            '"qd"true' in decoded_data or  # Quiz done = true
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
        if '"qd"true' in decoded_data or 'quiz_done":true' in decoded_data:
            # Look for actual score in completed quiz
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

