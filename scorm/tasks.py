"""
Celery tasks for Storyline completion fixing
"""
from celery import shared_task
from django.contrib.auth import get_user_model
from scorm.storyline_completion_fixer import StorylineCompletionFixer
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task
def fix_storyline_completion_async(username=None):
    """
    Asynchronous task to fix Storyline completion issues
    """
    try:
        logger.info(f"🔧 CELERY TASK: Starting Storyline completion fix for user: {username}")
        
        fixer = StorylineCompletionFixer()
        
        if username:
            try:
                user = User.objects.get(username=username)
                fixed, skipped = fixer.fix_user_attempts(user)
                logger.info(f"✅ CELERY TASK: Fixed {fixed} attempts for user {username}")
                return {
                    'success': True,
                    'user': username,
                    'fixed': fixed,
                    'skipped': skipped,
                    'errors': fixer.errors
                }
            except User.DoesNotExist:
                error_msg = f"User {username} not found"
                logger.error(f"❌ CELERY TASK: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
        else:
            fixed, skipped = fixer.fix_all_incomplete_attempts()
            logger.info(f"✅ CELERY TASK: Fixed {fixed} attempts globally")
            return {
                'success': True,
                'user': 'all',
                'fixed': fixed,
                'skipped': skipped,
                'errors': fixer.errors
            }
            
    except Exception as e:
        error_msg = f"Error in Storyline completion fix task: {str(e)}"
        logger.error(f"❌ CELERY TASK: {error_msg}")
        return {
            'success': False,
            'error': error_msg
        }


@shared_task
def schedule_storyline_completion_check():
    """
    Scheduled task to check for Storyline completion issues
    Runs periodically to catch any missed completion issues
    """
    try:
        logger.info("🔄 SCHEDULED TASK: Checking for Storyline completion issues")
        
        from scorm.models import ScormAttempt
        
        # Find recent incomplete attempts with suspend data
        from django.utils import timezone
        from datetime import timedelta
        
        recent_cutoff = timezone.now() - timedelta(hours=24)
        
        incomplete_attempts = ScormAttempt.objects.filter(
            lesson_status='incomplete',
            suspend_data__isnull=False,
            last_accessed__gte=recent_cutoff
        ).exclude(suspend_data='')
        
        if incomplete_attempts.count() == 0:
            logger.info("🔄 SCHEDULED TASK: No recent incomplete attempts found")
            return {
                'success': True,
                'message': 'No recent incomplete attempts found',
                'checked': 0,
                'fixed': 0
            }
        
        logger.info(f"🔄 SCHEDULED TASK: Found {incomplete_attempts.count()} recent incomplete attempts")
        
        fixer = StorylineCompletionFixer()
        fixed_count = 0
        
        for attempt in incomplete_attempts:
            success, reason = fixer.fix_attempt(attempt)
            if success:
                fixed_count += 1
                logger.info(f"🔄 SCHEDULED TASK: Fixed attempt {attempt.id} - {reason}")
        
        logger.info(f"✅ SCHEDULED TASK: Fixed {fixed_count} attempts")
        
        return {
            'success': True,
            'checked': incomplete_attempts.count(),
            'fixed': fixed_count,
            'errors': fixer.errors
        }
        
    except Exception as e:
        error_msg = f"Error in scheduled Storyline completion check: {str(e)}"
        logger.error(f"❌ SCHEDULED TASK: {error_msg}")
        return {
            'success': False,
            'error': error_msg
        }