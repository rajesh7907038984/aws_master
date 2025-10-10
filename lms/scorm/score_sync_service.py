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
            
            # Always update last_score with the current score
            topic_progress.last_score = Decimal(str(score_value))
            
            # Update best_score if this is better
            if topic_progress.best_score is None or score_value > float(topic_progress.best_score):
                topic_progress.best_score = Decimal(str(score_value))
            
            # Update completion status
            is_completed = scorm_attempt.lesson_status in ['completed', 'passed', 'failed']
            if is_completed and not topic_progress.completed:
                topic_progress.completed = True
                topic_progress.completion_method = 'scorm'
                topic_progress.completed_at = timezone.now()
            
            # Update attempts count
            topic_progress.attempts = max(topic_progress.attempts, scorm_attempt.attempt_number)
            
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
                'attempt_id': scorm_attempt.id
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
        
        # Priority 3: Progress percentage (if completed)
        if attempt.lesson_status in ['completed', 'passed'] and attempt.progress_percentage:
            scores.append(float(attempt.progress_percentage))
        
        # Return the highest score found
        return max(scores) if scores else None
    
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
