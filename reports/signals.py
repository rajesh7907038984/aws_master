from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in
from courses.models import CourseEnrollment
from quiz.models import QuizAttempt
from assignments.models import AssignmentSubmission
from discussions.models import Discussion, Comment
from .models import Event
import logging

logger = logging.getLogger(__name__)

@receiver(pre_save, sender=CourseEnrollment)
def track_completion_change(sender, instance, **kwargs):
    """Track original completion status before save"""
    if instance.pk:
        try:
            original = CourseEnrollment.objects.get(pk=instance.pk)
            instance._original_completed = original.completed
        except CourseEnrollment.DoesNotExist:
            instance._original_completed = None
    else:
        instance._original_completed = None

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log when a user logs in"""
    try:
        Event.objects.create(
            user=user,
            type='LOGIN',
            description=f"{user.get_full_name() or user.username} logged in"
        )
    except Exception as e:
        logger.error(f"Failed to log login event for user {user.id}: {str(e)}")

@receiver(post_save, sender=CourseEnrollment)
def log_course_enrollment(sender, instance, created, **kwargs):
    """Log when a user enrolls in or completes a course"""
    from core.utils.signal_coordination import SignalCoordinator
    
    if not SignalCoordinator.should_process_signal('logging', instance, created):
        return
        
    try:
        if created:
            # Course enrollment
            Event.objects.create(
                user=instance.user,
                course=instance.course,
                type='COURSE_START',
                description=f"{instance.user.get_full_name() or instance.user.username} enrolled in {instance.course.title}"
            )
        elif instance.completed and hasattr(instance, '_state') and instance._state.adding is False:
            # Course completion - check if completion status changed from False to True
            original_completed = getattr(instance, '_original_completed', None)
            if original_completed is False and instance.completed is True:
                # Only create event if completion status actually changed
                Event.objects.get_or_create(
                    user=instance.user,
                    course=instance.course,
                    type='COURSE_COMPLETE',
                    defaults={
                        'description': f"{instance.user.get_full_name() or instance.user.username} completed {instance.course.title}"
                    }
                )
    except Exception as e:
        logger.error(f"Failed to log course enrollment event for user {instance.user.id}: {str(e)}")

@receiver(post_save, sender=QuizAttempt)
def log_quiz_attempt(sender, instance, created, **kwargs):
    """Log when a user takes a quiz"""
    try:
        if created:
            Event.objects.create(
                user=instance.user,
                course=instance.quiz.course if hasattr(instance.quiz, 'course') else None,
                type='QUIZ_TAKE',
                description=f"{instance.user.get_full_name() or instance.user.username} took quiz: {instance.quiz.title}",
                metadata={
                    'quiz_id': instance.quiz.id,
                    'score': getattr(instance, 'score', None),
                    'passed': getattr(instance, 'passed', None)
                }
            )
    except Exception as e:
        logger.error(f"Failed to log quiz attempt event for user {instance.user.id}: {str(e)}")

@receiver(post_save, sender=AssignmentSubmission)
def log_assignment_submission(sender, instance, created, **kwargs):
    """Log when a user submits an assignment"""
    try:
        if created:
            Event.objects.create(
                user=instance.user,
                course=instance.assignment.course if hasattr(instance.assignment, 'course') else None,
                type='ASSIGNMENT_SUBMIT',
                description=f"{instance.user.get_full_name() or instance.user.username} submitted assignment: {instance.assignment.title}",
                metadata={
                    'assignment_id': instance.assignment.id,
                    'submission_id': instance.id
                }
            )
    except Exception as e:
        logger.error(f"Failed to log assignment submission event for user {instance.user.id}: {str(e)}")

@receiver(post_save, sender=Discussion)
def log_forum_post(sender, instance, created, **kwargs):
    """Log when a user creates a forum post"""
    try:
        if created:
            Event.objects.create(
                user=instance.created_by,
                course=instance.course if hasattr(instance, 'course') else None,
                type='FORUM_POST',
                description=f"{instance.created_by.get_full_name() or instance.created_by.username} created a forum post: {instance.title[:50]}...",
                metadata={
                    'discussion_id': instance.id,
                    'title': instance.title
                }
            )
    except Exception as e:
        logger.error(f"Failed to log forum post event for user {instance.created_by.id}: {str(e)}") 