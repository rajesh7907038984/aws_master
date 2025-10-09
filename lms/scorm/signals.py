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

logger = logging.getLogger(__name__)


@receiver(post_save, sender='scorm.ScormAttempt')
def auto_extract_score_on_save(sender, instance, created, **kwargs):
    """
    AUTOMATIC SCORE EXTRACTION - Runs every time SCORM attempt is saved
    Extracts score from suspend_data even if SCORM content doesn't report it
    NO USER ACTION REQUIRED - Completely automatic
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
    
    try:
        logger.info(f"🤖 AUTO-EXTRACT: Checking attempt {instance.id} for unreported scores...")
        
        # Decode and decompress suspend_data
        decoded_data = _decode_suspend_data(instance.suspend_data)
        
        if not decoded_data:
            return
        
        # Extract score from decoded data
        extracted_score = _extract_score_from_data(decoded_data)
        
        if extracted_score and extracted_score > 0:
            logger.info(f"✅ AUTO-EXTRACT: Found score {extracted_score} in suspend_data for attempt {instance.id}")
            
            # Update the score
            instance.score_raw = Decimal(str(extracted_score))
            
            # Set status based on score
            mastery_score = instance.scorm_package.mastery_score or 80
            if extracted_score >= mastery_score:
                instance.lesson_status = 'passed'
            else:
                instance.lesson_status = 'failed'
            
            # Save without triggering this signal again
            instance.save(update_fields=['score_raw', 'lesson_status'])
            
            # Update TopicProgress
            _update_topic_progress(instance, extracted_score)
            
            # Clear caches
            cache.clear()
            
            logger.info(f"✅ AUTO-EXTRACT: Successfully updated score to {extracted_score} for attempt {instance.id}")
        
    except Exception as e:
        logger.error(f"❌ AUTO-EXTRACT: Error extracting score for attempt {instance.id}: {str(e)}")


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
    """Extract score from decoded suspend data"""
    try:
        # Pattern 1: Storyline "ps80""100r"2,s50" - extract the ACTUAL score s50 (NOT the passing score ps80)
        ps_pattern = re.search(r'ps\d+["\s]*\d+["\s]*r["\s]*\d+[,\s]*s(\d+)', decoded_data)
        if ps_pattern:
            score = float(ps_pattern.group(1))
            if 0 <= score <= 100:
                logger.info(f"Found Storyline quiz score: {score}")
                return score
        
        # Pattern 2: Standalone "s50" but NOT "ps80" (avoid passing score)
        # Look for ,s50 or "s50 to ensure it's the score not mastery score
        standalone_score = re.search(r'[,"\s]s(\d+)[,"\s]', decoded_data)
        if standalone_score:
            score = float(standalone_score.group(1))
            if 0 <= score <= 100:
                logger.info(f"Found standalone score: s{score}")
                return score
        
        # Pattern 3: Look for "score":value
        score_match = re.search(r'"(?:score|p)"\s*:\s*(\d+\.?\d*)', decoded_data, re.IGNORECASE)
        if score_match:
            return float(score_match.group(1))
        
        # Pattern 4: Look for percentage
        percent_match = re.search(r'(\d+)%', decoded_data)
        if percent_match:
            return float(percent_match.group(1))
        
        # Pattern 5: Look for quiz/test score
        quiz_match = re.search(r'"(?:quiz|test|exam)"\s*:\s*(\d+\.?\d*)', decoded_data, re.IGNORECASE)
        if quiz_match:
            return float(quiz_match.group(1))
        
        return None
        
    except Exception as e:
        logger.debug(f"Could not extract score: {e}")
        return None


def _update_topic_progress(attempt, score_value):
    """Update TopicProgress with extracted score"""
    try:
        from courses.models import TopicProgress
        
        topic = attempt.scorm_package.topic
        
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=attempt.user,
            topic=topic
        )
        
        # Update last score
        old_last = topic_progress.last_score
        old_best = topic_progress.best_score
        
        topic_progress.last_score = float(score_value)
        
        # Update best score if this is better
        if not topic_progress.best_score or float(score_value) > topic_progress.best_score:
            topic_progress.best_score = float(score_value)
        
        topic_progress.save()
        
        logger.info(f"📊 AUTO-EXTRACT: Updated TopicProgress - last_score: {old_last} → {topic_progress.last_score}, best_score: {old_best} → {topic_progress.best_score}")
        
    except Exception as e:
        logger.error(f"Error updating TopicProgress: {e}")

