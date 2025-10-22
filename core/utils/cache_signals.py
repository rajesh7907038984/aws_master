"""
Cache invalidation signals for dashboard performance optimization
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from users.models import CustomUser
from courses.models import Course, CourseEnrollment
from branches.models import Branch
from .dashboard_cache import DashboardCache
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CustomUser)
def invalidate_user_cache(sender, instance, created, **kwargs):
    """Invalidate cache when user data changes"""
    try:
        # Clear user-specific cache
        DashboardCache.clear_user_cache(instance.id)
        
        # Clear branch cache if user has a branch
        if instance.branch_id:
            DashboardCache.clear_branch_cache(instance.branch_id)
        
        # Clear global cache for global stats
        if created or instance.role in ['globaladmin', 'superadmin']:
            DashboardCache.clear_all_dashboard_cache()
            
        logger.info(f"Cache invalidated for user {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating user cache: {e}")


@receiver(post_delete, sender=CustomUser)
def invalidate_user_cache_on_delete(sender, instance, **kwargs):
    """Invalidate cache when user is deleted"""
    try:
        # Clear user-specific cache
        DashboardCache.clear_user_cache(instance.id)
        
        # Clear branch cache if user had a branch
        if instance.branch_id:
            DashboardCache.clear_branch_cache(instance.branch_id)
        
        # Clear global cache
        DashboardCache.clear_all_dashboard_cache()
        
        logger.info(f"Cache invalidated for deleted user {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating cache on user delete: {e}")


@receiver(post_save, sender=CourseEnrollment)
def invalidate_enrollment_cache(sender, instance, created, **kwargs):
    """Invalidate cache when enrollment data changes"""
    from .signal_coordination import SignalCoordinator
    
    if not SignalCoordinator.should_process_signal('cache_invalidation', instance, created):
        return
        
    try:
        # Clear user cache for the enrolled user
        if instance.user_id:
            DashboardCache.clear_user_cache(instance.user_id)
        
        # Clear branch cache if user has a branch
        if instance.user and instance.user.branch_id:
            DashboardCache.clear_branch_cache(instance.user.branch_id)
        
        # Clear instructor cache if course has an instructor
        if instance.course and instance.course.instructor_id:
            DashboardCache.clear_user_cache(instance.course.instructor_id)
        
        # Also clear cache for all instructors who have access to this course through groups
        if instance.course:
            from groups.models import GroupMembership
            group_instructors = CustomUser.objects.filter(
                role='instructor',
                group_memberships__group__course_groups__course=instance.course,
                group_memberships__is_active=True
            ).distinct()
            for instructor in group_instructors:
                DashboardCache.clear_user_cache(instructor.id)
                logger.info(f"Cleared instructor cache for group-access instructor {instructor.id}")
        
        # Clear global cache for completion rate changes
        DashboardCache.clear_all_dashboard_cache()
        
        logger.info(f"Cache invalidated for enrollment {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating enrollment cache: {e}")


@receiver(post_delete, sender=CourseEnrollment)
def invalidate_enrollment_cache_on_delete(sender, instance, **kwargs):
    """Invalidate cache when enrollment is deleted"""
    try:
        # Clear user cache for the enrolled user
        if instance.user_id:
            DashboardCache.clear_user_cache(instance.user_id)
        
        # Clear branch cache if user has a branch
        if instance.user and instance.user.branch_id:
            DashboardCache.clear_branch_cache(instance.user.branch_id)
        
        # Clear instructor cache if course has an instructor
        if instance.course and instance.course.instructor_id:
            DashboardCache.clear_user_cache(instance.course.instructor_id)
        
        # Also clear cache for all instructors who have access to this course through groups
        if instance.course:
            from groups.models import GroupMembership
            group_instructors = CustomUser.objects.filter(
                role='instructor',
                group_memberships__group__course_groups__course=instance.course,
                group_memberships__is_active=True
            ).distinct()
            for instructor in group_instructors:
                DashboardCache.clear_user_cache(instructor.id)
                logger.info(f"Cleared instructor cache for group-access instructor {instructor.id}")
        
        # Clear global cache
        DashboardCache.clear_all_dashboard_cache()
        
        logger.info(f"Cache invalidated for deleted enrollment {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating cache on enrollment delete: {e}")


@receiver(post_save, sender=Course)
def invalidate_course_cache(sender, instance, created, **kwargs):
    """Invalidate cache when course data changes"""
    try:
        # Clear instructor cache if course has an instructor
        if instance.instructor_id:
            DashboardCache.clear_user_cache(instance.instructor_id)
        
        # Also clear cache for all instructors who have access to this course through groups
        from groups.models import GroupMembership
        group_instructors = CustomUser.objects.filter(
            role='instructor',
            group_memberships__group__course_groups__course=instance,
            group_memberships__is_active=True
        ).distinct()
        for instructor in group_instructors:
            DashboardCache.clear_user_cache(instructor.id)
            logger.info(f"Cleared instructor cache for group-access instructor {instructor.id}")
        
        # Clear branch cache if course has a branch
        if instance.branch_id:
            DashboardCache.clear_branch_cache(instance.branch_id)
        
        # Clear global cache for course count changes
        if created:
            DashboardCache.clear_all_dashboard_cache()
        
        logger.info(f"Cache invalidated for course {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating course cache: {e}")


@receiver(post_delete, sender=Course)
def invalidate_course_cache_on_delete(sender, instance, **kwargs):
    """Invalidate cache when course is deleted"""
    try:
        # Clear instructor cache if course had an instructor
        if instance.instructor_id:
            DashboardCache.clear_user_cache(instance.instructor_id)
        
        # Also clear cache for all instructors who had access to this course through groups
        from groups.models import GroupMembership
        group_instructors = CustomUser.objects.filter(
            role='instructor',
            group_memberships__group__course_groups__course=instance,
            group_memberships__is_active=True
        ).distinct()
        for instructor in group_instructors:
            DashboardCache.clear_user_cache(instructor.id)
            logger.info(f"Cleared instructor cache for group-access instructor {instructor.id}")
        
        # Clear branch cache if course had a branch
        if instance.branch_id:
            DashboardCache.clear_branch_cache(instance.branch_id)
        
        # Clear global cache
        DashboardCache.clear_all_dashboard_cache()
        
        logger.info(f"Cache invalidated for deleted course {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating cache on course delete: {e}")


@receiver(post_save, sender=Branch)
def invalidate_branch_cache(sender, instance, created, **kwargs):
    """Invalidate cache when branch data changes"""
    try:
        # Clear branch-specific cache
        DashboardCache.clear_branch_cache(instance.id)
        
        # Clear global cache for branch count changes
        if created:
            DashboardCache.clear_all_dashboard_cache()
        
        logger.info(f"Cache invalidated for branch {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating branch cache: {e}")


@receiver(post_delete, sender=Branch)
def invalidate_branch_cache_on_delete(sender, instance, **kwargs):
    """Invalidate cache when branch is deleted"""
    try:
        # Clear branch-specific cache
        DashboardCache.clear_branch_cache(instance.id)
        
        # Clear global cache
        DashboardCache.clear_all_dashboard_cache()
        
        logger.info(f"Cache invalidated for deleted branch {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating cache on branch delete: {e}")


# Gradebook-specific cache invalidation signals
@receiver(post_save, sender='gradebook.Grade')
def invalidate_gradebook_cache(sender, instance, **kwargs):
    """Invalidate gradebook cache when grades are updated"""
    try:
        from django.core.cache import cache
        
        # Clear gradebook cache for the specific course
        if instance.course_id:
            # Clear all gradebook cache patterns for this course
            cache_patterns = [
                f"gradebook:scores:course:{instance.course_id}:*",
                f"gradebook:*:course:{instance.course_id}",
            ]
            
            # Since we can't use pattern matching in all cache backends,
            # we'll clear the entire cache to be safe
            cache.clear()
            
        logger.info(f"Gradebook cache invalidated for grade {instance.id} in course {instance.course_id}")
    except Exception as e:
        logger.error(f"Error invalidating gradebook cache: {e}")


@receiver(post_save, sender='assignments.AssignmentSubmission')
def invalidate_gradebook_cache_on_submission(sender, instance, **kwargs):
    """Invalidate gradebook cache when submissions are updated"""
    try:
        from django.core.cache import cache
        
        # Clear gradebook cache when submission is graded
        if instance.grade is not None and instance.assignment and instance.assignment.course:
            cache.clear()  # Clear all cache to ensure consistency
            
        logger.info(f"Gradebook cache invalidated for submission {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating gradebook cache on submission: {e}")


@receiver(post_save, sender='quiz.QuizAttempt')
def invalidate_quiz_cache(sender, instance, **kwargs):
    """Invalidate gradebook and quiz cache when quiz attempts are updated"""
    try:
        from django.core.cache import cache
        
        # Clear cache when quiz attempt is completed or scored
        if instance.is_completed and instance.quiz and instance.quiz.course:
            cache.clear()  # Clear all cache to ensure consistency
            
        logger.info(f"Quiz cache invalidated for attempt {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating quiz cache on attempt: {e}")


@receiver(post_save, sender='discussions.Discussion')
def invalidate_discussion_cache(sender, instance, **kwargs):
    """Invalidate cache when discussions are updated"""
    try:
        from django.core.cache import cache
        
        # Clear cache when discussion status or rubric changes
        if instance.course:
            cache.clear()  # Clear all cache to ensure consistency
            
        logger.info(f"Discussion cache invalidated for discussion {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating discussion cache: {e}")


@receiver(post_save, sender='conferences.Conference')
def invalidate_conference_cache(sender, instance, **kwargs):
    """Invalidate cache when conferences are updated"""
    try:
        from django.core.cache import cache
        
        # Clear cache when conference status or rubric changes
        if instance.course:
            cache.clear()  # Clear all cache to ensure consistency
            
        logger.info(f"Conference cache invalidated for conference {instance.id}")
    except Exception as e:
        logger.error(f"Error invalidating conference cache: {e}") 