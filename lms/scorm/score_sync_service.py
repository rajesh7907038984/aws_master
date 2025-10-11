"""
SCORM Score Synchronization Service
Provides automatic real-time synchronization between SCORM attempts and TopicProgress
Ensures consistency across all score tracking systems
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)


class ScormScoreSyncService:
    """
    Centralized service for SCORM score synchronization
    Ensures scores are always consistent between ScormAttempt and TopicProgress
    """
    
    @staticmethod
    @transaction.atomic
    def sync_score(scorm_attempt: 'ScormAttempt', force: bool = False) -> bool:
        """
        Synchronize score from ScormAttempt to TopicProgress
        This is the single source of truth for score synchronization
        
        Args:
            scorm_attempt: The ScormAttempt instance to sync
            force: Force sync even if attempt seems incomplete
            
        Returns:
            bool: True if sync was performed, False otherwise
        """
        try:
            # Import here to avoid circular imports
            from courses.models import TopicProgress
            from .models import ScormAttempt
            
            # Get the related topic
            if not hasattr(scorm_attempt, 'scorm_package') or not scorm_attempt.scorm_package.topic:
                logger.warning(f"ScormAttempt {scorm_attempt.id} has no associated topic")
                return False
            
            topic = scorm_attempt.scorm_package.topic
            
            # Get or create TopicProgress
            topic_progress, created = TopicProgress.objects.get_or_create(
                user=scorm_attempt.user,
                topic=topic,
                defaults={
                    'attempts': 0,
                    'last_accessed': timezone.now()
                }
            )
            
            # Determine if we should sync the score
            should_sync = force or ScormScoreSyncService._should_sync_score(scorm_attempt)
            
            if not should_sync:
                logger.debug(f"Skipping sync for attempt {scorm_attempt.id} - not ready for sync")
                return False
            
            # Extract the most accurate score
            score_value = ScormScoreSyncService._extract_best_score(scorm_attempt)
            
            if score_value is None:
                logger.warning(f"No valid score found for attempt {scorm_attempt.id}")
                return False
            
            # Update TopicProgress with the score
            old_last_score = topic_progress.last_score
            old_best_score = topic_progress.best_score
            
            # Update best_score if this is better
            if topic_progress.best_score is None or score_value > float(topic_progress.best_score):
                topic_progress.best_score = Decimal(str(score_value))
            
            # CRITICAL FIX: For SCORM content, always use best_score as last_score
            # This prevents score downgrade when users retake content
            # Gradebook displays last_score, so it should show their best achievement
            topic_progress.last_score = topic_progress.best_score if topic_progress.best_score is not None else Decimal(str(score_value))
            
            # Update completion status
            is_completed = scorm_attempt.lesson_status in ['completed', 'passed', 'failed']
            if is_completed and not topic_progress.completed:
                topic_progress.completed = True
                topic_progress.completion_method = 'scorm'
                topic_progress.completed_at = timezone.now()
            
            # Update attempts count
            topic_progress.attempts = max(topic_progress.attempts or 0, scorm_attempt.attempt_number)
            
            # Update total time spent from SCORM attempt
            if scorm_attempt.total_time:
                try:
                    # Parse SCORM time format (hhhh:mm:ss.ss or PT1H30M45S)
                    time_seconds = ScormScoreSyncService._parse_scorm_time(scorm_attempt.total_time)
                    if time_seconds > 0:
                        # Update with the latest time value (don't add, as total_time is cumulative)
                        topic_progress.total_time_spent = max(topic_progress.total_time_spent or 0, int(time_seconds))
                        logger.info(f"Updated time for attempt {scorm_attempt.id}: {time_seconds}s")
                except Exception as e:
                    logger.warning(f"Could not parse time from attempt {scorm_attempt.id}: {e}")
            
            # Update last accessed
            topic_progress.last_accessed = scorm_attempt.last_accessed
            
            # Update progress data
            if not topic_progress.progress_data:
                topic_progress.progress_data = {}
            
            topic_progress.progress_data.update({
                'scorm_status': scorm_attempt.lesson_status,
                'success_status': scorm_attempt.success_status,
                'last_sync': timezone.now().isoformat(),
                'sync_source': 'ScormScoreSyncService',
                'attempt_id': scorm_attempt.id,
                'total_time': scorm_attempt.total_time
            })
            
            # Save the changes
            topic_progress.save()
            
            # Clear cache to ensure fresh data
            cache_keys = [
                f'gradebook_course_{topic.courses.first().id}_*' if topic.courses.exists() else None,
                f'topic_progress_{topic.id}_*',
                f'user_progress_{scorm_attempt.user.id}_*'
            ]
            for key in cache_keys:
                if key:
                    cache.delete_pattern(key)
            
            logger.info(
                f"✅ SYNC SUCCESS: Attempt {scorm_attempt.id} -> TopicProgress {topic_progress.id} | "
                f"Score: {old_last_score} -> {topic_progress.last_score} | "
                f"Best: {old_best_score} -> {topic_progress.best_score} | "
                f"Status: {scorm_attempt.lesson_status}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ SYNC ERROR: Failed to sync attempt {scorm_attempt.id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    @staticmethod
    def _should_sync_score(attempt: 'ScormAttempt') -> bool:
        """
        Determine if an attempt should have its score synced
        """
        # Always sync if attempt is completed/passed/failed
        if attempt.lesson_status in ['completed', 'passed', 'failed']:
            return True
        
        # CRITICAL FIX: Sync if there's ANY valid score (including 0)
        if attempt.score_raw is not None:
            return True
        
        # Check for score in CMI data (including scores of 0)
        if attempt.cmi_data:
            cmi_score = attempt.cmi_data.get('cmi.score.raw') or attempt.cmi_data.get('cmi.core.score.raw')
            if cmi_score is not None and cmi_score != '':
                try:
                    score_val = float(cmi_score)
                    # CRITICAL FIX: Accept any valid score >= 0 (not just > 0)
                    if score_val >= 0:
                        return True
                except:
                    pass
        
        # CRITICAL FIX: Also check for any score data in attempt even if incomplete
        # This ensures first visit scores are synced
        if hasattr(attempt, 'score_raw') and attempt.score_raw is not None:
            return True
            
        # Don't sync only if there's truly no score data at all
        return False
    
    @staticmethod
    def _extract_best_score(attempt: 'ScormAttempt') -> Optional[float]:
        """
        Extract the best available score from a SCORM attempt
        Checks multiple sources in priority order
        """
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
        
        # Priority 3: Progress percentage (for both completed and in-progress)
        # This handles slide-based SCORM content that tracks completion by slides
        if attempt.progress_percentage:
            progress_score = float(attempt.progress_percentage)
            # Only use progress as score if it's reasonable (0-100)
            if 0 <= progress_score <= 100:
                scores.append(progress_score)
                logger.info(f"Using progress_percentage as score: {progress_score}% for attempt {attempt.id}")
        
        # Priority 4: Calculate from slide completion (for slide-based SCORM)
        if not scores and attempt.completed_slides and attempt.total_slides:
            try:
                # Extract completed slides count
                if isinstance(attempt.completed_slides, list):
                    completed_count = len(attempt.completed_slides)
                else:
                    completed_count = len(attempt.completed_slides.split(',')) if attempt.completed_slides else 0
                
                total_slides = int(attempt.total_slides)
                if total_slides > 0:
                    slide_completion_score = (completed_count / total_slides) * 100
                    scores.append(slide_completion_score)
                    logger.info(f"Calculated score from slides: {completed_count}/{total_slides} = {slide_completion_score}% for attempt {attempt.id}")
            except Exception as e:
                logger.warning(f"Could not calculate score from slides for attempt {attempt.id}: {e}")
        
        # Priority 5: Extract from suspend_data (enhanced for multiple SCORM package types)
        if not scores and attempt.suspend_data and len(attempt.suspend_data) > 10:
            try:
                import re
                import json
                
                # Try to decode JSON-encoded suspend_data first
                decoded_data = None
                try:
                    suspend_json = json.loads(attempt.suspend_data)
                    if 'd' in suspend_json and isinstance(suspend_json['d'], list):
                        # Decode the data array to string
                        decoded_data = ''.join([chr(x) for x in suspend_json['d'] if x < 256])
                        logger.info(f"Decoded JSON suspend_data for attempt {attempt.id}, length: {len(decoded_data)}")
                except:
                    # If not JSON, use raw suspend_data
                    decoded_data = attempt.suspend_data
                
                if decoded_data:
                    # Look for progress patterns in decoded data
                    progress_patterns = [
                        r'progress[=:](\d+)',
                        r'"progress":\s*(\d+)',
                        r'progress["\']?\s*:\s*(\d+)',
                        r'completion[=:](\d+)',
                        r'completion["\']?\s*:\s*(\d+)'
                    ]
                    
                    for pattern in progress_patterns:
                        progress_match = re.search(pattern, decoded_data, re.IGNORECASE)
                        if progress_match:
                            suspend_score = float(progress_match.group(1))
                            if 0 <= suspend_score <= 100:
                                scores.append(suspend_score)
                                logger.info(f"Extracted score from suspend_data pattern '{pattern}': {suspend_score}% for attempt {attempt.id}")
                                break
                    
                    # If no progress found, look for slide completion patterns
                    if not scores:
                        slide_patterns = [
                            r'completed_slides[=:]([^&]+).*?total_slides[=:](\d+)',
                            r'"completed_slides":\s*"([^"]+)".*?"total_slides":\s*(\d+)',
                            r'completed[=:]([^&]+).*?total[=:](\d+)',
                            r'slides_completed[=:]([^&]+).*?slides_total[=:](\d+)'
                        ]
                        
                        for pattern in slide_patterns:
                            slide_match = re.search(pattern, decoded_data, re.IGNORECASE | re.DOTALL)
                            if slide_match:
                                try:
                                    completed_str = slide_match.group(1)
                                    total = int(slide_match.group(2))
                                    
                                    # Parse completed slides
                                    if ',' in completed_str:
                                        completed = len([s for s in completed_str.split(',') if s.strip()])
                                    else:
                                        completed = 1 if completed_str.strip() else 0
                                    
                                    if total > 0:
                                        slide_score = round((completed / total) * 100, 2)
                                        scores.append(slide_score)
                                        logger.info(f"Calculated score from suspend_data pattern '{pattern}': {completed}/{total} = {slide_score}% for attempt {attempt.id}")
                                        break
                                except Exception as e:
                                    logger.warning(f"Error parsing slide pattern '{pattern}' for attempt {attempt.id}: {e}")
                                    continue
            except Exception as e:
                logger.warning(f"Could not extract score from suspend_data for attempt {attempt.id}: {e}")
        
        # Priority 6: Check CMI data for progress information
        if not scores and attempt.cmi_data:
            try:
                # Check for progress in CMI data
                progress_keys = [
                    'cmi.progress_measure',
                    'cmi.core.progress_measure', 
                    'cmi.completion_threshold',
                    'cmi.core.completion_threshold'
                ]
                
                for key in progress_keys:
                    if key in attempt.cmi_data:
                        progress_value = attempt.cmi_data[key]
                        if progress_value and progress_value != '':
                            try:
                                progress_float = float(progress_value)
                                if 0 <= progress_float <= 1:
                                    cmi_score = round(progress_float * 100, 2)
                                    scores.append(cmi_score)
                                    logger.info(f"Using CMI {key}: {cmi_score}% for attempt {attempt.id}")
                                    break
                                elif 0 <= progress_float <= 100:
                                    scores.append(round(progress_float, 2))
                                    logger.info(f"Using CMI {key}: {progress_float}% for attempt {attempt.id}")
                                    break
                            except:
                                continue
            except Exception as e:
                logger.warning(f"Could not extract from CMI data for attempt {attempt.id}: {e}")
        
        # Return the highest score found
        return max(scores) if scores else None
    
    @staticmethod
    def _parse_scorm_time(time_str: str) -> int:
        """
        Parse SCORM time format to seconds
        Supports both SCORM 1.2 (hhhh:mm:ss.ss) and SCORM 2004 (PT1H30M45S) formats
        
        Args:
            time_str: Time string in SCORM format
            
        Returns:
            int: Total seconds
        """
        try:
            if not time_str or time_str == '':
                return 0
            
            # Check if it's SCORM 2004 ISO 8601 duration format (PT1H30M45S)
            if time_str.startswith('PT'):
                # Remove PT prefix
                duration_str = time_str[2:]
                
                hours = 0
                minutes = 0
                seconds = 0
                
                # Parse hours
                if 'H' in duration_str:
                    h_index = duration_str.index('H')
                    hours = int(duration_str[:h_index])
                    duration_str = duration_str[h_index+1:]
                
                # Parse minutes
                if 'M' in duration_str:
                    m_index = duration_str.index('M')
                    minutes = int(duration_str[:m_index])
                    duration_str = duration_str[m_index+1:]
                
                # Parse seconds
                if 'S' in duration_str:
                    s_index = duration_str.index('S')
                    seconds = float(duration_str[:s_index])
                
                return int(hours * 3600 + minutes * 60 + seconds)
            
            # SCORM 1.2 time format (hhhh:mm:ss.ss)
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return int(hours * 3600 + minutes * 60 + seconds)
            
            return 0
        except (ValueError, IndexError, TypeError) as e:
            logger.warning(f"Could not parse SCORM time '{time_str}': {e}")
            return 0
    
    @staticmethod
    def batch_sync_course_scores(course_id: int) -> Dict[str, Any]:
        """
        Sync all SCORM scores for a specific course
        Used for maintenance and verification
        """
        from courses.models import Course, Topic
        from .models import ScormAttempt
        
        results = {
            'total_attempts': 0,
            'synced': 0,
            'failed': 0,
            'skipped': 0
        }
        
        try:
            # Get all topics in the course with SCORM packages
            topics = Topic.objects.filter(
                courses__id=course_id,
                content_type='SCORM',
                scorm_package__isnull=False
            ).distinct()
            
            for topic in topics:
                # Get all attempts for this topic's SCORM package
                attempts = ScormAttempt.objects.filter(
                    scorm_package=topic.scorm_package
                ).select_related('user', 'scorm_package')
                
                for attempt in attempts:
                    results['total_attempts'] += 1
                    
                    try:
                        if ScormScoreSyncService.sync_score(attempt):
                            results['synced'] += 1
                        else:
                            results['skipped'] += 1
                    except Exception as e:
                        results['failed'] += 1
                        logger.error(f"Failed to sync attempt {attempt.id}: {str(e)}")
            
            logger.info(f"Batch sync completed for course {course_id}: {results}")
            
        except Exception as e:
            logger.error(f"Batch sync failed for course {course_id}: {str(e)}")
        
        return results
    
    @staticmethod
    def verify_score_consistency(user_id: int, topic_id: int) -> Dict[str, Any]:
        """
        Verify and fix score consistency between ScormAttempt and TopicProgress
        """
        from courses.models import TopicProgress, Topic
        from .models import ScormAttempt
        
        result = {
            'consistent': True,
            'scorm_score': None,
            'topic_progress_score': None,
            'action_taken': None
        }
        
        try:
            topic = Topic.objects.get(id=topic_id)
            
            # Get latest SCORM attempt
            latest_attempt = ScormAttempt.objects.filter(
                user_id=user_id,
                scorm_package=topic.scorm_package
            ).order_by('-last_accessed').first()
            
            if not latest_attempt:
                result['action_taken'] = 'No SCORM attempt found'
                return result
            
            # Get TopicProgress
            topic_progress = TopicProgress.objects.filter(
                user_id=user_id,
                topic_id=topic_id
            ).first()
            
            # Extract scores
            scorm_score = ScormScoreSyncService._extract_best_score(latest_attempt)
            topic_score = float(topic_progress.last_score) if topic_progress and topic_progress.last_score else None
            
            result['scorm_score'] = scorm_score
            result['topic_progress_score'] = topic_score
            
            # Check consistency
            if scorm_score != topic_score:
                result['consistent'] = False
                # Fix the inconsistency
                if ScormScoreSyncService.sync_score(latest_attempt, force=True):
                    result['action_taken'] = 'Score synchronized successfully'
                else:
                    result['action_taken'] = 'Failed to synchronize score'
            else:
                result['action_taken'] = 'Scores are already consistent'
            
        except Exception as e:
            result['action_taken'] = f'Error: {str(e)}'
            result['consistent'] = False
        
        return result
