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
from .package_analyzer import ScormPackageAnalyzer

logger = logging.getLogger(__name__)


@receiver(post_save, sender='scorm.ScormPackage')
def auto_analyze_scorm_package(sender, instance, created, **kwargs):
    """
    Automatically analyze new SCORM packages to ensure auto-scoring is enabled
    and automatically detect and fix launch URLs
    """
    if created:
        try:
            logger.info(f" Auto-analyzing new SCORM package: {instance.title}")
            
            # Get manifest content for analysis
            manifest_content = None
            if instance.manifest_data:
                manifest_content = instance.manifest_data.get('raw_manifest', '')
            
            # Analyze package
            package_metadata = ScormPackageAnalyzer.analyze_package(
                instance.manifest_data or {},
                manifest_content
            )
            
            # Update package metadata
            instance.package_metadata = package_metadata
            instance.save()
            
            auto_scoring = package_metadata.get('needs_auto_scoring', False)
            logger.info(f" Package analysis complete - Auto-scoring: {auto_scoring}")
            
            # AUTOMATIC LAUNCH URL DETECTION
            try:
                from scorm.s3_direct import scorm_s3
                from scorm.universal_scorm_handler import UniversalSCORMHandler
                
                logger.info(f" Auto-detecting launch URL for package {instance.id}")
                
                # Get package files from S3
                package_files = scorm_s3.list_package_files(instance)
                logger.info(f" Found {len(package_files)} files in package")
                
                # Detect correct launch file
                detected_launch_file = UniversalSCORMHandler.detect_launch_file(package_files)
                
                if detected_launch_file:
                    logger.info(f" Detected launch file: {detected_launch_file}")
                    
                    # Check if current launch URL is correct
                    if instance.launch_url != detected_launch_file:
                        logger.info(f" Launch URL mismatch detected!")
                        logger.info(f" Current: {instance.launch_url}")
                        logger.info(f" Detected: {detected_launch_file}")
                        
                        # Update the launch URL automatically
                        old_launch_url = instance.launch_url
                        instance.launch_url = detected_launch_file
                        instance.save()
                        
                        logger.info(f" Auto-fixed launch URL: {old_launch_url} → {detected_launch_file}")
                    else:
                        logger.info(f" Launch URL is already correct: {instance.launch_url}")
                else:
                    logger.warning(f" Could not auto-detect launch file for package {instance.id}")
                    
            except Exception as launch_error:
                logger.error(f" Failed to auto-detect launch URL for package {instance.id}: {str(launch_error)}")
            
        except Exception as e:
            logger.error(f" Failed to auto-analyze package {instance.id}: {str(e)}")


@receiver(post_save, sender='scorm.ScormAttempt')
def dynamic_score_processor(sender, instance, created, **kwargs):
    """
    DYNAMIC SCORE PROCESSOR - Automatically handles all SCORM formats
    Uses centralized ScormScoreSyncService for consistent score synchronization
    
    FIXED: Better recursion prevention using raw update instead of save
    """
    # Import the sync service
    from .score_sync_service import ScormScoreSyncService
    
    # Skip if this is a new attempt creation
    if created:
        return
    
    # Skip if this save was triggered by the API handler or another component
    # Use a single consistent flag
    if getattr(instance, '_skip_signal', False):
        return
    
    try:
        logger.debug(f"SYNC: Processing score synchronization for attempt {instance.id}...")
        
        # Use the centralized sync service
        # The sync service will use update() instead of save() to avoid triggering signals
        success = ScormScoreSyncService.sync_score(instance)
        
        if success:
            logger.info(f"SYNC: Successfully synchronized score for attempt {instance.id}")
        else:
            logger.debug(f"SYNC: No score synchronization needed for attempt {instance.id}")
        
    except Exception as e:
        logger.error(f"SYNC: Error synchronizing attempt {instance.id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())


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
        # FIXED: Mark as completed if passed, completed, OR failed (student attempted the content)
        is_completed = attempt.lesson_status in ['passed', 'completed', 'failed']
        
        if not is_completed:
            logger.info(f" AUTO-EXTRACT: SCORM not completed yet (status: {attempt.lesson_status}) - skipping TopicProgress score update")
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
        
        logger.info(f" AUTO-EXTRACT: SCORM completed - Updated TopicProgress - last_score: {old_last} → {topic_progress.last_score}, best_score: {old_best} → {topic_progress.best_score}")
        
    except Exception as e:
        logger.error(f"Error updating TopicProgress: {e}")

