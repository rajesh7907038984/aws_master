from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
import logging
from .models import AssignmentSubmission
from courses.models import TopicProgress
from assignments.models import TopicAssignment

logger = logging.getLogger(__name__)

@receiver(pre_save, sender=AssignmentSubmission)
def update_graded_fields(sender, instance, **kwargs):
    """Update graded_at field when grade changes"""
    if instance.pk:  # If this is an update, not a new submission
        try:
            old_instance = AssignmentSubmission.objects.get(pk=instance.pk)
            if old_instance.grade != instance.grade:
                instance.graded_at = timezone.now()
        except AssignmentSubmission.DoesNotExist:
            pass

@receiver(post_save, sender=AssignmentSubmission)
def update_topic_progress(sender, instance, **kwargs):
    """Update topic progress when submission is graded or submitted"""
    # Get topic assignments related to this assignment
    topic_assignments = TopicAssignment.objects.filter(assignment=instance.assignment)
    
    # If no topic assignments, there's nothing to update
    if not topic_assignments.exists():
        return
    
    try:
        for topic_assignment in topic_assignments:
            topic = topic_assignment.topic
            
            # Get or create the topic progress for this user and topic
            topic_progress, created = TopicProgress.objects.get_or_create(
                user=instance.user,
                topic=topic,
                defaults={
                    'completed': False,
                    'progress_data': {}
                }
            )
            
            # Update the progress data with the submission info
            topic_progress.progress_data.update({
                'submission_id': instance.id,
                'submission_status': instance.status,
                'submitted_at': timezone.now().isoformat(),
            })
            
            # Add grade information if available
            if instance.grade is not None:
                topic_progress.progress_data.update({
                    'grade': float(instance.grade),
                    'max_score': float(instance.assignment.max_score),
                    'percentage': float(instance.grade) / float(instance.assignment.max_score) * 100
                })
                topic_progress.last_score = instance.grade
                
                # Update best score if this is better
                if topic_progress.best_score is None or instance.grade > topic_progress.best_score:
                    topic_progress.best_score = instance.grade
            
            # Mark as completed when submitted or graded
            if instance.status in ['submitted', 'graded']:
                if not topic_progress.completed:
                    # Use the centralized mark_complete method for consistency
                    topic_progress.mark_complete('auto')
                    
                    # Add assignment-specific completion info to progress data
                    topic_progress.progress_data.update({
                        'assignment_submission_id': instance.id,
                        'assignment_status': instance.status,
                        'assignment_completed_at': timezone.now().isoformat()
                    })
                    
                    topic_progress.save()
                    
                    # Check if course is now completed as a result of this topic completion
                    topic_progress._check_course_completion()
                else:
                    # Already completed, just update the progress data
                    topic_progress.progress_data.update({
                        'assignment_submission_id': instance.id,
                        'assignment_status': instance.status
                    })
                    topic_progress.save()
            
    except Exception as e:
        # Log error but don't fail the save operation
        logger.error(f"Error updating topic progress: {e}") 