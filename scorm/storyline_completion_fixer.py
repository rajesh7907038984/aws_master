"""
Storyline Completion Auto-Fixer
Automatically detects and fixes slide-based SCORM completion issues
"""
import logging
from django.utils import timezone
from django.db import transaction
from scorm.models import ScormAttempt
from courses.models import TopicProgress

logger = logging.getLogger(__name__)


class StorylineCompletionFixer:
    """
    Automatically detects and fixes Storyline SCORM completion issues
    """
    
    # Completion indicators to look for in suspend data
    COMPLETION_INDICATORS = [
        'complete', 'finished', 'done', 'passed', 'failed',
        'qd"true', 'qd":true', 'quiz_done":true', 'assessment_done":true',
        'lesson_done":true', 'course_done":true', '100', 'completed'
    ]
    
    # Minimum slides to consider completion
    MIN_SLIDES_FOR_COMPLETION = 3
    
    # Slides threshold for assumed complete course
    ASSUMED_COMPLETE_SLIDES = 5
    
    def __init__(self):
        self.fixed_count = 0
        self.skipped_count = 0
        self.errors = []
    
    def fix_attempt(self, attempt):
        """
        Fix a single SCORM attempt if it shows completion evidence
        """
        try:
            if not attempt.suspend_data:
                return False, "No suspend data"
            
            # Analyze suspend data
            analysis = self._analyze_suspend_data(attempt.suspend_data)
            
            if not analysis['should_be_completed']:
                return False, analysis['reason']
            
            # Apply the fix
            success = self._apply_completion_fix(attempt, analysis)
            
            if success:
                self.fixed_count += 1
                logger.info(f"✅ STORYLINE FIX: Fixed attempt {attempt.id} - {analysis['reason']}")
                return True, analysis['reason']
            else:
                return False, "Failed to apply fix"
                
        except Exception as e:
            error_msg = f"Error fixing attempt {attempt.id}: {str(e)}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False, error_msg
    
    def _analyze_suspend_data(self, suspend_data):
        """
        Analyze suspend data for completion evidence
        """
        visited_count = suspend_data.count('Visited')
        
        # Check for completion indicators
        found_indicators = []
        for indicator in self.COMPLETION_INDICATORS:
            if indicator in suspend_data:
                found_indicators.append(indicator)
        
        # Determine if should be completed
        should_be_completed = False
        reason = ""
        
        # Pattern 1: Multiple slides visited + completion indicators
        if visited_count >= self.MIN_SLIDES_FOR_COMPLETION and found_indicators:
            should_be_completed = True
            reason = f"Storyline completion detected: {visited_count} slides visited + indicators: {found_indicators}"
        
        # Pattern 2: 100% completion indicator + slides visited
        elif visited_count >= self.MIN_SLIDES_FOR_COMPLETION and '100' in suspend_data:
            should_be_completed = True
            reason = f"Storyline completion detected: {visited_count} slides visited + 100% indicator"
        
        # Pattern 3: Many slides visited (assume complete course)
        elif visited_count >= self.ASSUMED_COMPLETE_SLIDES:
            should_be_completed = True
            reason = f"Storyline completion detected: {visited_count} slides visited (assumed complete course)"
        
        # Pattern 4: Quiz completion indicators without slide count
        elif found_indicators and any(ind in ['qd"true', 'qd":true', 'quiz_done":true'] for ind in found_indicators):
            should_be_completed = True
            reason = f"Storyline quiz completion detected: indicators: {found_indicators}"
        
        else:
            reason = f"Not enough evidence: {visited_count} slides, indicators: {found_indicators}"
        
        return {
            'should_be_completed': should_be_completed,
            'reason': reason,
            'visited_count': visited_count,
            'found_indicators': found_indicators
        }
    
    def _apply_completion_fix(self, attempt, analysis):
        """
        Apply completion fix to attempt and related records
        """
        try:
            with transaction.atomic():
                # Update SCORM attempt
                attempt.lesson_status = 'completed'
                attempt.completion_status = 'completed'
                attempt.success_status = 'passed'
                
                # Set completion score if not already set
                if attempt.score_raw is None:
                    attempt.score_raw = 100.0
                
                # Update CMI data
                attempt.cmi_data['cmi.core.lesson_status'] = 'completed'
                attempt.cmi_data['cmi.completion_status'] = 'completed'
                attempt.cmi_data['cmi.success_status'] = 'passed'
                attempt.cmi_data['cmi.core.score.raw'] = str(attempt.score_raw)
                
                # Update detailed tracking
                if not attempt.detailed_tracking:
                    attempt.detailed_tracking = {}
                
                attempt.detailed_tracking.update({
                    'storyline_completion_detected': True,
                    'completion_reason': analysis['reason'],
                    'visited_slides_count': analysis['visited_count'],
                    'completion_indicators': analysis['found_indicators'],
                    'completion_source': 'storyline_auto_fixer',
                    'completion_timestamp': timezone.now().isoformat()
                })
                
                attempt.save()
                
                # Update TopicProgress
                self._update_topic_progress(attempt, analysis)
                
                return True
                
        except Exception as e:
            logger.error(f"Error applying completion fix: {str(e)}")
            return False
    
    def _update_topic_progress(self, attempt, analysis):
        """
        Update TopicProgress with completion data
        """
        try:
            progress, created = TopicProgress.objects.get_or_create(
                user=attempt.user,
                topic=attempt.scorm_package.topic
            )
            
            progress.completed = True
            progress.last_score = 100.0
            
            # Update best score
            if progress.best_score is None or 100.0 > progress.best_score:
                progress.best_score = 100.0
            
            progress.attempts += 1
            
            # Update progress data
            if not progress.progress_data:
                progress.progress_data = {}
            
            progress.progress_data.update({
                'score_raw': 100.0,
                'lesson_status': 'completed',
                'completion_status': 'completed',
                'success_status': 'passed',
                'storyline_auto_fix': True,
                'fix_reason': analysis['reason'],
                'fix_timestamp': timezone.now().isoformat(),
                'visited_slides_count': analysis['visited_count'],
                'completion_indicators': analysis['found_indicators']
            })
            
            progress.save()
            
            logger.info(f"✅ TOPICPROGRESS: Updated topic {attempt.scorm_package.topic.id} for user {attempt.user.username}")
            
        except Exception as e:
            logger.error(f"Error updating TopicProgress: {str(e)}")
    
    def fix_user_attempts(self, user):
        """
        Fix all incomplete Storyline attempts for a specific user
        """
        logger.info(f"🔧 STORYLINE FIXER: Starting batch fix for user {user.username}")
        
        # Find incomplete attempts with suspend data
        incomplete_attempts = ScormAttempt.objects.filter(
            user=user,
            lesson_status='incomplete',
            suspend_data__isnull=False
        ).exclude(suspend_data='')
        
        logger.info(f"Found {incomplete_attempts.count()} incomplete attempts to check")
        
        for attempt in incomplete_attempts:
            success, reason = self.fix_attempt(attempt)
            if not success:
                self.skipped_count += 1
                logger.debug(f"⏭️  SKIPPED attempt {attempt.id}: {reason}")
        
        logger.info(f"✅ STORYLINE FIXER: Fixed {self.fixed_count}, skipped {self.skipped_count}")
        return self.fixed_count, self.skipped_count
    
    def fix_all_incomplete_attempts(self):
        """
        Fix all incomplete Storyline attempts across all users
        """
        logger.info("🔧 STORYLINE FIXER: Starting global batch fix")
        
        # Find all incomplete attempts with suspend data
        incomplete_attempts = ScormAttempt.objects.filter(
            lesson_status='incomplete',
            suspend_data__isnull=False
        ).exclude(suspend_data='')
        
        logger.info(f"Found {incomplete_attempts.count()} incomplete attempts to check globally")
        
        for attempt in incomplete_attempts:
            success, reason = self.fix_attempt(attempt)
            if not success:
                self.skipped_count += 1
                logger.debug(f"⏭️  SKIPPED attempt {attempt.id}: {reason}")
        
        logger.info(f"✅ STORYLINE FIXER: Global fix complete - Fixed {self.fixed_count}, skipped {self.skipped_count}")
        return self.fixed_count, self.skipped_count
    
    def get_summary(self):
        """
        Get summary of fixes applied
        """
        return {
            'fixed_count': self.fixed_count,
            'skipped_count': self.skipped_count,
            'errors': self.errors,
            'total_processed': self.fixed_count + self.skipped_count
        }


def auto_fix_storyline_completion(user=None):
    """
    Convenience function to auto-fix Storyline completion issues
    """
    fixer = StorylineCompletionFixer()
    
    if user:
        fixed, skipped = fixer.fix_user_attempts(user)
    else:
        fixed, skipped = fixer.fix_all_incomplete_attempts()
    
    return fixer.get_summary()
