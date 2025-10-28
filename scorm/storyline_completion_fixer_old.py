"""
SCORM Completion Auto-Fixer
Automatically detects and fixes SCORM completion issues based on suspend data
"""
import logging
from django.utils import timezone
from django.db import transaction
from scorm.models import ScormAttempt
from courses.models import TopicProgress

logger = logging.getLogger(__name__)


class ScormCompletionFixer:
    """
    Automatically detects and fixes SCORM completion issues based on suspend data
    """
    
    # Completion indicators to look for in suspend data
    # STRICT: Only actual completion status indicators, NOT score indicators
    COMPLETION_INDICATORS = [
        'complete', 'finished', 'done', 'passed', 'failed', 'completed',
        'qd"true', 'qd":true', 'quiz_done":true', 'assessment_done":true',
        'lesson_done":true', 'course_done":true'
        # REMOVED: '100' - this is a score indicator, not a completion indicator
        # Score indicators can appear even with minimal engagement
    ]

    def __init__(self):
        self.fixed_count = 0
        self.skipped_count = 0
        self.errors = []
    
    def _get_schema_default(self, field, version='1.2'):
        """Get schema-defined default value for a field based on SCORM version"""
        from .cmi_data_handler import CMIDataHandler
        return CMIDataHandler.get_schema_default(field, version)
    
    def fix_attempt(self, attempt):
        """
        Fix a single SCORM attempt based ONLY on suspend data analysis
        """
        try:
            if not attempt.suspend_data:
                return False, "No suspend data"
            
            # Check suspend data completion criteria
            package_analysis = self._check_package_completion_criteria(attempt)
            
            if not package_analysis['should_be_completed']:
                return False, package_analysis['reason']
            
            # Apply the fix
            success = self._apply_completion_fix(attempt, package_analysis)
            
            if success:
                self.fixed_count += 1
                logger.info(f"✅ SUSPEND DATA FIX: Fixed attempt {attempt.id} - {package_analysis['reason']}")
                return True, package_analysis['reason']
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
        SUSPEND DATA ONLY: Focus only on completion indicators
        """
        # Check for completion indicators
        found_indicators = []
        for indicator in self.COMPLETION_INDICATORS:
            if indicator in suspend_data:
                found_indicators.append(indicator)
        
        return {
            'should_be_completed': len(found_indicators) > 0,
            'reason': f"Suspend data analysis: indicators: {found_indicators}",
            'found_indicators': found_indicators
        }
    
    def _check_package_completion_criteria(self, attempt):
        """
        SUSPEND DATA ONLY completion validation
        Focus ONLY on suspend data analysis - ignore SCORM status, scores, and slide counts
        """
        # ONLY use suspend data analysis
        suspend_data = attempt.suspend_data or ''
        
        # Check for actual completion indicators (not score indicators)
        found_completion_indicators = []
        for indicator in self.COMPLETION_INDICATORS:
            if indicator in suspend_data:
                found_completion_indicators.append(indicator)
        
        completion_reasons = []
        
        # SUSPEND DATA ONLY completion logic
        if found_completion_indicators:
            completion_reasons.append(f"Suspend data completion indicators: {found_completion_indicators}")
        
        # Determine completion based ONLY on suspend data indicators
        should_be_completed = len(completion_reasons) > 0
        reason = "; ".join(completion_reasons) if completion_reasons else f"No completion indicators found in suspend data (indicators: {found_completion_indicators})"
        
        return {
            'should_be_completed': should_be_completed,
            'reason': reason,
            'found_completion_indicators': found_completion_indicators,
            'completion_reasons': completion_reasons
        }
    
    
    def _apply_completion_fix(self, attempt, analysis):
        """
        Apply completion fix to attempt and related records based on package-specific criteria
        """
        try:
            with transaction.atomic():
                # Determine completion status and score based on package type
                is_slide_based = analysis.get('is_slide_based', False)
                
                # Get SCORM version for proper schema defaults
                scorm_version = attempt.scorm_package.version
                
                if is_slide_based:
                    # SLIDE-BASED PACKAGE: Pass/Fail logic
                    # If completion criteria met: Pass (100%), if not: Fail (0%)
                    if analysis['should_be_completed']:
                        # PASS: Slide completion achieved
                        attempt.lesson_status = 'completed'
                        attempt.completion_status = 'completed'
                        attempt.success_status = 'passed'
                        attempt.score_raw = 100.0
                        completion_type = 'slide_based_pass'
                    else:
                        # FAIL: Slide completion not achieved
                        attempt.lesson_status = 'failed'
                        attempt.completion_status = self._get_schema_default('cmi.completion_status', scorm_version)
                        attempt.success_status = 'failed'
                        attempt.score_raw = 0.0
                        completion_type = 'slide_based_fail'
                else:
                    # SCORE-BASED PACKAGE: Use actual score
                    if analysis['should_be_completed']:
                        attempt.lesson_status = 'completed'
                        attempt.completion_status = 'completed'
                        attempt.success_status = 'passed'
                        # Keep original score if available, otherwise set to 100
                        if attempt.score_raw is None:
                            attempt.score_raw = 100.0
                        completion_type = 'score_based_pass'
                    else:
                        attempt.lesson_status = 'failed'
                        attempt.completion_status = self._get_schema_default('cmi.completion_status', scorm_version)
                        attempt.success_status = 'failed'
                        attempt.score_raw = 0.0
                        completion_type = 'score_based_fail'
                
                # Update CMI data
                attempt.cmi_data['cmi.core.lesson_status'] = attempt.lesson_status
                attempt.cmi_data['cmi.completion_status'] = attempt.completion_status
                attempt.cmi_data['cmi.success_status'] = attempt.success_status
                attempt.cmi_data['cmi.core.score.raw'] = str(attempt.score_raw)
                
                # Update detailed tracking
                if not attempt.detailed_tracking:
                    attempt.detailed_tracking = {}
                
                attempt.detailed_tracking.update({
                    'storyline_completion_detected': True,
                    'completion_reason': analysis['reason'],
                    'completion_source': 'package_specific_criteria',
                    'completion_type': completion_type,
                    'completion_timestamp': timezone.now().isoformat(),
                    'mastery_score': float(analysis.get('mastery_score', 0)) if analysis.get('mastery_score') else None,
                    'completion_reasons': analysis.get('completion_reasons', []),
                    'is_slide_based': is_slide_based,
                    'visited_count': analysis.get('visited_count', 0),
                    'selected_count': analysis.get('selected_count', 0)
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
        Update TopicProgress with completion data based on package-specific criteria
        """
        try:
            progress, created = TopicProgress.objects.get_or_create(
                user=attempt.user,
                topic=attempt.scorm_package.topic
            )
            
            progress.completed = True
            progress.completion_method = 'scorm'
            progress.last_score = attempt.score_raw or 100.0
            
            # Update best score
            if progress.best_score is None or (attempt.score_raw and attempt.score_raw > progress.best_score):
                progress.best_score = attempt.score_raw or 100.0
            
            progress.attempts += 1
            
            # Update progress data
            if not progress.progress_data:
                progress.progress_data = {}
            
            progress.progress_data.update({
                'score_raw': float(attempt.score_raw) if attempt.score_raw else 100.0,
                'lesson_status': 'completed',
                'completion_status': 'completed',
                'success_status': 'passed',
                'package_specific_completion': True,
                'completion_reason': analysis['reason'],
                'mastery_score': float(analysis.get('mastery_score', 0)) if analysis.get('mastery_score') else None,
                'completion_reasons': analysis.get('completion_reasons', []),
                'fix_timestamp': timezone.now().isoformat()
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
            lesson_status=self._get_schema_default('cmi.core.lesson_status'),
            suspend_data__isnull=False
        ).exclude(suspend_data='')
        
        logger.info(f"Found {incomplete_attempts.count()} incomplete attempts to check")
        
        for attempt in incomplete_attempts:
            success, reason = self.fix_attempt(attempt)
            if not success:
                self.skipped_count += 1
                logger.debug(f"⏭️  SKIPPED attempt {attempt.id}: {reason}")
        
        logger.info(f"✅ SCORM FIXER: Fixed {self.fixed_count}, skipped {self.skipped_count}")
        return self.fixed_count, self.skipped_count
    
    def fix_all_incomplete_attempts(self):
        """
        Fix all incomplete Storyline attempts across all users
        """
        logger.info("🔧 SCORM FIXER: Starting global batch fix")
        
        # Find all incomplete attempts with suspend data
        incomplete_attempts = ScormAttempt.objects.filter(
            lesson_status=self._get_schema_default('cmi.core.lesson_status'),
            suspend_data__isnull=False
        ).exclude(suspend_data='')
        
        logger.info(f"Found {incomplete_attempts.count()} incomplete attempts to check globally")
        
        for attempt in incomplete_attempts:
            success, reason = self.fix_attempt(attempt)
            if not success:
                self.skipped_count += 1
                logger.debug(f"⏭️  SKIPPED attempt {attempt.id}: {reason}")
        
        logger.info(f"✅ SCORM FIXER: Global fix complete - Fixed {self.fixed_count}, skipped {self.skipped_count}")
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


def auto_fix_scorm_completion(user=None):
    """
    Convenience function to auto-fix SCORM completion issues
    """
    fixer = ScormCompletionFixer()
    
    if user:
        fixed, skipped = fixer.fix_user_attempts(user)
    else:
        fixed, skipped = fixer.fix_all_incomplete_attempts()
    
    return fixer.get_summary()
