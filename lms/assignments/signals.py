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
                # Mark that grading notification should be sent
                instance._grade_changed = True
                instance._old_grade = old_instance.grade
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
    
    # Send grading notification if grade was changed
    if hasattr(instance, '_grade_changed') and instance._grade_changed and instance.grade is not None:
        try:
            from lms_notifications.utils import send_notification
            from django.urls import reverse
            
            # Calculate percentage
            percentage = (float(instance.grade) / float(instance.assignment.max_score)) * 100 if instance.assignment.max_score > 0 else 0
            
            # Prepare grading notification message
            grading_message = f"""
            <h2>Assignment Graded</h2>
            <p>Dear {instance.user.first_name or instance.user.username},</p>
            <p>Your assignment has been graded by the instructor.</p>
            <p><strong>Assignment Details:</strong></p>
            <ul>
                <li><strong>Assignment:</strong> {instance.assignment.title}</li>
                <li><strong>Grade:</strong> {instance.grade} / {instance.assignment.max_score}</li>
                <li><strong>Percentage:</strong> {percentage:.1f}%</li>
                <li><strong>Status:</strong> {instance.get_status_display()}</li>
                {f'<li><strong>Graded At:</strong> {instance.graded_at.strftime("%B %d, %Y at %I:%M %p")}</li>' if instance.graded_at else ''}
            </ul>
            {f'<div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #4CAF50; margin: 15px 0;"><p><strong>Instructor Feedback:</strong></p><p>{instance.feedback}</p></div>' if instance.feedback else ''}
            <p>You can view your submission and detailed feedback by clicking the button below.</p>
            <p>Keep up the good work!</p>
            <p>Best regards,<br>The LMS Team</p>
            """
            
            # Send notification
            notification = send_notification(
                recipient=instance.user,
                notification_type_name='assignment_graded',
                title=f"Assignment Graded: {instance.assignment.title}",
                message=grading_message,
                short_message=f"Your assignment '{instance.assignment.title}' has been graded. Score: {instance.grade}/{instance.assignment.max_score}",
                priority='normal',
                action_url=f"/assignments/{instance.assignment.id}/submission/{instance.id}/",
                action_text="View Grade",
                related_assignment=instance.assignment,
                send_email=True
            )
            
            if notification:
                logger.info(f"Grading notification sent to user: {instance.user.username} for assignment: {instance.assignment.title}")
            else:
                logger.warning(f"Grading notification created but email may not have been sent for user: {instance.user.username}")
                
        except Exception as e:
            logger.error(f"Error sending grading notification to {instance.user.username}: {str(e)}") 