"""
Celery tasks for quiz maintenance and cleanup
"""
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
from quiz.models import QuizAttempt, UserAnswer, Quiz
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def cleanup_expired_quiz_attempts(self):
    """
    Background task to clean up expired and stale quiz attempts.
    This should run every 30 minutes to keep the system clean.
    """
    try:
        logger.info("Starting quiz attempts cleanup...")
        
        expired_count = 0
        stale_count = 0
        
        # Prevent multiple cleanup tasks from running simultaneously
        lock_key = "quiz_cleanup_lock"
        if cache.get(lock_key):
            logger.info("Quiz cleanup already running, skipping...")
            return {"status": "skipped", "reason": "already_running"}
        
        # Set lock for 10 minutes
        cache.set(lock_key, True, 600)
        
        try:
            with transaction.atomic():
                # Clean expired attempts first
                expired_count = _cleanup_expired_attempts()
                
                # Clean stale attempts (inactive for 2+ hours)
                stale_count = _cleanup_stale_attempts()
                
                # Clean orphaned answers
                orphaned_count = _cleanup_orphaned_answers()
                
                total_cleaned = expired_count + stale_count + orphaned_count
                
                logger.info(f"Quiz cleanup completed: {expired_count} expired, {stale_count} stale, {orphaned_count} orphaned")
                
                return {
                    "status": "success",
                    "expired_attempts": expired_count,
                    "stale_attempts": stale_count,
                    "orphaned_answers": orphaned_count,
                    "total_cleaned": total_cleaned
                }
                
        finally:
            # Release lock
            cache.delete(lock_key)
            
    except Exception as e:
        logger.error(f"Quiz cleanup task failed: {str(e)}")
        raise self.retry(countdown=300, exc=e)


@shared_task(bind=True, max_retries=2)
def cleanup_quiz_attempts_for_user(self, user_id, quiz_id=None):
    """
    Clean up quiz attempts for a specific user.
    Used when user starts a new quiz attempt.
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.get(id=user_id)
        logger.info(f"Cleaning quiz attempts for user {user.username} (ID: {user_id})")
        
        # Build queryset
        queryset = QuizAttempt.objects.filter(
            user_id=user_id,
            is_completed=False
        )
        
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
        
        # Clean expired attempts
        expired_attempts = []
        for attempt in queryset.select_related('quiz'):
            if attempt.is_expired():
                expired_attempts.append(attempt.id)
        
        # Clean stale attempts (inactive for 1+ hour)
        stale_time = timezone.now() - timedelta(hours=1)
        stale_attempts = queryset.filter(last_activity__lt=stale_time)
        
        cleaned_count = 0
        
        if expired_attempts or stale_attempts.exists():
            with transaction.atomic():
                # Delete answers for expired attempts
                if expired_attempts:
                    UserAnswer.objects.filter(attempt_id__in=expired_attempts).delete()
                    QuizAttempt.objects.filter(id__in=expired_attempts).delete()
                    cleaned_count += len(expired_attempts)
                
                # Delete stale attempts and their answers
                if stale_attempts.exists():
                    stale_count = stale_attempts.count()
                    UserAnswer.objects.filter(attempt__in=stale_attempts).delete()
                    stale_attempts.delete()
                    cleaned_count += stale_count
        
        logger.info(f"Cleaned {cleaned_count} quiz attempts for user {user.username}")
        
        return {
            "status": "success",
            "user_id": user_id,
            "quiz_id": quiz_id,
            "cleaned_count": cleaned_count
        }
        
    except Exception as e:
        logger.error(f"User-specific quiz cleanup failed: {str(e)}")
        raise self.retry(countdown=60, exc=e)


def _cleanup_expired_attempts():
    """Helper function to clean up expired attempts"""
    expired_attempts = []
    
    # Get all incomplete attempts and check expiration
    incomplete_attempts = QuizAttempt.objects.filter(
        is_completed=False
    ).select_related('quiz')
    
    for attempt in incomplete_attempts:
        if attempt.is_expired():
            expired_attempts.append(attempt.id)
    
    if expired_attempts:
        # Delete associated answers first
        UserAnswer.objects.filter(attempt_id__in=expired_attempts).delete()
        
        # Delete the attempts
        QuizAttempt.objects.filter(id__in=expired_attempts).delete()
        
        logger.info(f"Cleaned up {len(expired_attempts)} expired quiz attempts")
    
    return len(expired_attempts)


def _cleanup_stale_attempts():
    """Helper function to clean up stale attempts"""
    # Consider attempts stale if inactive for 2+ hours
    stale_time = timezone.now() - timedelta(hours=2)
    
    stale_attempts = QuizAttempt.objects.filter(
        is_completed=False,
        last_activity__lt=stale_time
    )
    
    count = stale_attempts.count()
    
    if count > 0:
        # Delete associated answers first
        UserAnswer.objects.filter(attempt__in=stale_attempts).delete()
        
        # Delete the attempts
        stale_attempts.delete()
        
        logger.info(f"Cleaned up {count} stale quiz attempts")
    
    return count


def _cleanup_orphaned_answers():
    """Helper function to clean up orphaned user answers"""
    # Find answers where the attempt no longer exists
    orphaned_answers = UserAnswer.objects.filter(attempt__isnull=True)
    count = orphaned_answers.count()
    
    if count > 0:
        orphaned_answers.delete()
        logger.info(f"Cleaned up {count} orphaned user answers")
    
    return count


@shared_task
def quiz_health_check():
    """
    Periodic health check for quiz system.
    Monitors for issues and reports statistics.
    """
    try:
        # Count incomplete attempts by age
        now = timezone.now()
        
        stats = {
            "total_incomplete_attempts": QuizAttempt.objects.filter(is_completed=False).count(),
            "attempts_1h_old": QuizAttempt.objects.filter(
                is_completed=False,
                start_time__lt=now - timedelta(hours=1)
            ).count(),
            "attempts_1d_old": QuizAttempt.objects.filter(
                is_completed=False, 
                start_time__lt=now - timedelta(days=1)
            ).count(),
            "total_orphaned_answers": UserAnswer.objects.filter(attempt__isnull=True).count(),
        }
        
        logger.info(f"Quiz health check: {stats}")
        
        # Alert if too many old attempts exist
        if stats["attempts_1d_old"] > 50:
            logger.warning(f"High number of day-old incomplete attempts: {stats['attempts_1d_old']}")
        
        return {
            "status": "success",
            "timestamp": now.isoformat(),
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Quiz health check failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }
