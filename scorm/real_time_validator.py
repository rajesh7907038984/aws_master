"""
Real-time SCORM Score Validator
Continuously monitors and validates SCORM score synchronization
Automatically fixes issues as they occur
"""
import logging
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
from .models import ScormAttempt
from courses.models import TopicProgress
from datetime import timedelta

logger = logging.getLogger(__name__)


class ScormScoreValidator:
    """
    Real-time validator that ensures SCORM scores are properly synchronized
    across all models and immediately fixes any discrepancies
    """
    
    @staticmethod
    def validate_and_sync_attempt(attempt_id):
        """
        Validate a specific SCORM attempt and sync if needed
        Returns: (is_valid, was_fixed, details)
        """
        try:
            attempt = ScormAttempt.objects.get(id=attempt_id)
            
            # Check for basic data consistency
            issues = []
            fixed = False
            
            # Issue 1: Has suspend data but no score/completion
            if (attempt.suspend_data and len(attempt.suspend_data) > 50 and
                not attempt.score_raw and 
                attempt.lesson_status in ['not_attempted', 'incomplete']):
                
                logger.info(f"Validator: Attempt {attempt_id} has substantial suspend data but no score - processing")
                processor = DynamicScormScoreProcessor(attempt)
                
                if processor.process_and_sync_score():
                    issues.append("Fixed: Extracted missing score from suspend data")
                    fixed = True
                else:
                    issues.append("Warning: Has suspend data but no extractable score")
            
            # Issue 2: ScormAttempt has score but TopicProgress doesn't
            if attempt.score_raw:
                topic_progress = TopicProgress.objects.filter(
                    user=attempt.user,
                    topic=attempt.scorm_package.topic
                ).first()
                
                if not topic_progress:
                    issues.append("Error: ScormAttempt has score but TopicProgress missing")
                    # Create missing TopicProgress
                    try:
                        TopicProgress.objects.create(
                            user=attempt.user,
                            topic=attempt.scorm_package.topic,
                            last_score=float(attempt.score_raw),
                            best_score=float(attempt.score_raw),
                            completed=attempt.lesson_status in ['completed', 'passed'],
                            completion_method='scorm',
                            last_accessed=timezone.now(),
                            progress_data={
                                'scorm_attempt_id': attempt.id,
                                'auto_created': True,
                                'sync_method': 'validator',
                                'sync_timestamp': timezone.now().isoformat(),
                            }
                        )
                        issues.append("Fixed: Created missing TopicProgress")
                        fixed = True
                    except Exception as e:
                        issues.append(f"Error: Failed to create TopicProgress: {str(e)}")
                
                elif topic_progress.last_score != float(attempt.score_raw):
                    issues.append(f"Warning: Score mismatch - Attempt:{attempt.score_raw}, Topic:{topic_progress.last_score}")
                    # Fix the mismatch
                    try:
                        topic_progress.last_score = float(attempt.score_raw)
                        if topic_progress.best_score is None or float(attempt.score_raw) > topic_progress.best_score:
                            topic_progress.best_score = float(attempt.score_raw)
                        topic_progress.save(update_fields=['last_score', 'best_score'])
                        issues.append("Fixed: Synchronized score mismatch")
                        fixed = True
                    except Exception as e:
                        issues.append(f"Error: Failed to fix score mismatch: {str(e)}")
            
            # Issue 3: Completion status inconsistency
            if (attempt.lesson_status in ['passed', 'completed'] and
                attempt.score_raw and attempt.score_raw > 0):
                topic_progress = TopicProgress.objects.filter(
                    user=attempt.user,
                    topic=attempt.scorm_package.topic
                ).first()
                
                if topic_progress and not topic_progress.completed:
                    issues.append("Warning: SCORM completed but TopicProgress not marked as completed")
                    try:
                        topic_progress.completed = True
                        topic_progress.completion_method = 'scorm'
                        topic_progress.completed_at = timezone.now()
                        topic_progress.save(update_fields=['completed', 'completion_method', 'completed_at'])
                        issues.append("Fixed: Marked TopicProgress as completed")
                        fixed = True
                    except Exception as e:
                        issues.append(f"Error: Failed to mark TopicProgress as completed: {str(e)}")
            
            return len(issues) == 0, fixed, issues
            
        except Exception as e:
            logger.error(f"Validator: Error validating attempt {attempt_id}: {str(e)}")
            return False, False, [f"Error: Validation failed - {str(e)}"]
    
    @staticmethod
    def validate_recent_attempts(hours=1):
        """
        Validate all SCORM attempts from the last N hours
        Automatically fixes any issues found
        """
        since = timezone.now() - timedelta(hours=hours)
        
        recent_attempts = ScormAttempt.objects.filter(
            last_accessed__gte=since
        ).order_by('-last_accessed')
        
        total_checked = 0
        issues_found = 0
        fixes_applied = 0
        
        logger.info(f"Validator: Checking {recent_attempts.count()} recent attempts from last {hours} hours")
        
        for attempt in recent_attempts:
            is_valid, was_fixed, details = ScormScoreValidator.validate_and_sync_attempt(attempt.id)
            total_checked += 1
            
            if not is_valid:
                issues_found += 1
                logger.warning(f"Validator: Issues found in attempt {attempt.id}: {'; '.join(details)}")
            
            if was_fixed:
                fixes_applied += 1
                logger.info(f"Validator: Applied fixes to attempt {attempt.id}")
        
        logger.info(f"Validator: Checked {total_checked} attempts, found {issues_found} issues, applied {fixes_applied} fixes")
        
        return {
            'checked': total_checked,
            'issues': issues_found,
            'fixes': fixes_applied
        }
    
    @staticmethod
    def validate_all_scores():
        """
        Comprehensive validation of all SCORM scores in the system
        Use sparingly - this can be resource intensive
        """
        all_attempts = ScormAttempt.objects.filter(
            suspend_data__isnull=False
        ).exclude(suspend_data='').order_by('-last_accessed')
        
        total_checked = 0
        issues_found = 0
        fixes_applied = 0
        
        logger.info(f"Validator: Starting comprehensive validation of {all_attempts.count()} attempts")
        
        for attempt in all_attempts:
            is_valid, was_fixed, details = ScormScoreValidator.validate_and_sync_attempt(attempt.id)
            total_checked += 1
            
            if not is_valid:
                issues_found += 1
            
            if was_fixed:
                fixes_applied += 1
            
            # Progress indicator for large datasets
            if total_checked % 10 == 0:
                logger.info(f"Validator: Progress - {total_checked}/{all_attempts.count()}")
        
        logger.info(f"Validator: Comprehensive validation complete - checked {total_checked}, issues {issues_found}, fixes {fixes_applied}")
        
        return {
            'checked': total_checked,
            'issues': issues_found,
            'fixes': fixes_applied
        }
