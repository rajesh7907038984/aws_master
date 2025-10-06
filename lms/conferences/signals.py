from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import ConferenceParticipant, Conference
from courses.models import TopicProgress, Topic
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ConferenceParticipant)
def update_topic_progress_on_conference_participation(sender, instance, **kwargs):
    """Update topic progress when user participates in a conference"""
    # Only process when user has joined the meeting or is active
    if instance.participation_status not in ['joined_meeting', 'active_in_meeting', 'meeting_ended', 'sync_completed']:
        return
    
    # Skip if no user (guest participants)
    if not instance.user:
        return
    
    try:
        # Find topics that contain this conference
        topics = Topic.objects.filter(conference=instance.conference)
        
        for topic in topics:
            # Get or create topic progress
            topic_progress, created = TopicProgress.objects.get_or_create(
                user=instance.user,
                topic=topic,
                defaults={
                    'completed': False,
                    'progress_data': {}
                }
            )
            
            # Initialize progress_data if not exists
            if not topic_progress.progress_data:
                topic_progress.progress_data = {}
            
            # Update progress data with conference info
            topic_progress.progress_data.update({
                'conference_participant_id': instance.id,
                'conference_participation_status': instance.participation_status,
                'conference_join_method': instance.join_method,
                'conference_participated_at': timezone.now().isoformat(),
                'conference_title': instance.conference.title
            })
            
            # Mark as completed when user has joined the meeting or is active
            if instance.participation_status in ['joined_meeting', 'active_in_meeting', 'meeting_ended', 'sync_completed']:
                if not topic_progress.completed:
                    topic_progress.mark_complete('auto')
                    
                    # Add conference-specific completion info to progress data
                    topic_progress.progress_data.update({
                        'conference_completed': True,
                        'conference_completed_at': timezone.now().isoformat(),
                        'conference_completion_method': 'auto'
                    })
                    
                    # Log the completion
                    logger.info(f"Conference participation auto-marked topic {topic.id} as complete for user {instance.user.username}")
            
            topic_progress.save()
            
            # Check if course is now completed as a result of this topic completion
            if topic_progress.completed:
                topic_progress._check_course_completion()
                
    except Exception as e:
        # Log error but don't fail the save operation
        logger.error(f"Error updating topic progress for conference participation: {e}")


@receiver(post_save, sender=Conference)
def send_conference_notifications(sender, instance, created, **kwargs):
    """
    Send email notifications for conference events
    """
    if created and instance.course:
        try:
            # Import here to avoid circular imports
            from lms_notifications.utils import send_notification
            from courses.models import CourseEnrollment
            from django.urls import reverse
            
            # Get all enrolled students in the course
            enrollments = CourseEnrollment.objects.filter(
                course=instance.course,
                user__is_active=True
            ).select_related('user')
            
            # Format date and time
            conference_datetime = f"{instance.date.strftime('%B %d, %Y')} at {instance.start_time.strftime('%I:%M %p')}"
            if instance.end_time:
                conference_datetime += f" - {instance.end_time.strftime('%I:%M %p')}"
            
            for enrollment in enrollments:
                try:
                    # Prepare conference notification message
                    conference_message = f"""
                    <h2>New Conference Scheduled</h2>
                    <p>Dear {enrollment.user.first_name or enrollment.user.username},</p>
                    <p>A new conference has been scheduled for your course:</p>
                    <p><strong>Conference Details:</strong></p>
                    <ul>
                        <li><strong>Title:</strong> {instance.title}</li>
                        <li><strong>Course:</strong> {instance.course.title}</li>
                        <li><strong>Date & Time:</strong> {conference_datetime}</li>
                        <li><strong>Timezone:</strong> {instance.timezone}</li>
                        <li><strong>Platform:</strong> {instance.get_meeting_platform_display()}</li>
                    </ul>
                    {f'<div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #2196F3; margin: 15px 0;"><p><strong>Description:</strong></p><p>{instance.description}</p></div>' if instance.description else ''}
                    <p>Please mark your calendar and join the conference at the scheduled time.</p>
                    <p>We look forward to seeing you there!</p>
                    <p>Best regards,<br>The LMS Team</p>
                    """
                    
                    # Send notification
                    notification = send_notification(
                        recipient=enrollment.user,
                        notification_type_name='conference_reminder',
                        title=f"Conference Scheduled: {instance.title}",
                        message=conference_message,
                        short_message=f"A new conference '{instance.title}' has been scheduled for {instance.date.strftime('%B %d, %Y')}",
                        priority='normal',
                        action_url=f"/conferences/{instance.id}/",
                        action_text="View Conference Details",
                        send_email=True
                    )
                    
                    if notification:
                        logger.info(f"Conference notification sent to user: {enrollment.user.username} for conference: {instance.title}")
                    else:
                        logger.warning(f"Conference notification created but email may not have been sent for user: {enrollment.user.username}")
                        
                except Exception as e:
                    logger.error(f"Error sending conference notification to {enrollment.user.username}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error processing conference notifications: {str(e)}")


@receiver(pre_save, sender=Conference)
def send_conference_update_notifications(sender, instance, **kwargs):
    """
    Send notifications when conference details are updated
    """
    if instance.pk:  # Only for existing conferences
        try:
            old_instance = Conference.objects.get(pk=instance.pk)
            
            # Check if important details changed
            details_changed = (
                old_instance.date != instance.date or
                old_instance.start_time != instance.start_time or
                old_instance.end_time != instance.end_time or
                old_instance.meeting_link != instance.meeting_link
            )
            
            if details_changed and instance.course:
                # Mark that update notification should be sent
                instance._details_changed = True
                
        except Conference.DoesNotExist:
            pass


@receiver(post_save, sender=Conference)
def send_conference_update_email(sender, instance, created, **kwargs):
    """
    Send email notifications for conference updates
    """
    if not created and hasattr(instance, '_details_changed') and instance._details_changed and instance.course:
        try:
            # Import here to avoid circular imports
            from lms_notifications.utils import send_notification
            from courses.models import CourseEnrollment
            
            # Get all enrolled students in the course
            enrollments = CourseEnrollment.objects.filter(
                course=instance.course,
                user__is_active=True
            ).select_related('user')
            
            # Format date and time
            conference_datetime = f"{instance.date.strftime('%B %d, %Y')} at {instance.start_time.strftime('%I:%M %p')}"
            if instance.end_time:
                conference_datetime += f" - {instance.end_time.strftime('%I:%M %p')}"
            
            for enrollment in enrollments:
                try:
                    # Prepare conference update message
                    update_message = f"""
                    <h2>Conference Updated</h2>
                    <p>Dear {enrollment.user.first_name or enrollment.user.username},</p>
                    <p>The details for a conference in your course have been updated:</p>
                    <p><strong>Updated Conference Details:</strong></p>
                    <ul>
                        <li><strong>Title:</strong> {instance.title}</li>
                        <li><strong>Course:</strong> {instance.course.title}</li>
                        <li><strong>Date & Time:</strong> {conference_datetime}</li>
                        <li><strong>Timezone:</strong> {instance.timezone}</li>
                        <li><strong>Platform:</strong> {instance.get_meeting_platform_display()}</li>
                    </ul>
                    <div style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 15px 0;">
                        <p><strong> Important:</strong> Please update your calendar with the new details.</p>
                    </div>
                    {f'<div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #2196F3; margin: 15px 0;"><p><strong>Description:</strong></p><p>{instance.description}</p></div>' if instance.description else ''}
                    <p>We apologize for any inconvenience this may cause.</p>
                    <p>Best regards,<br>The LMS Team</p>
                    """
                    
                    # Send notification
                    notification = send_notification(
                        recipient=enrollment.user,
                        notification_type_name='conference_reminder',
                        title=f"Conference Updated: {instance.title}",
                        message=update_message,
                        short_message=f"Conference '{instance.title}' has been updated. Please check new details.",
                        priority='high',
                        action_url=f"/conferences/{instance.id}/",
                        action_text="View Updated Details",
                        send_email=True
                    )
                    
                    if notification:
                        logger.info(f"Conference update notification sent to user: {enrollment.user.username} for conference: {instance.title}")
                    else:
                        logger.warning(f"Conference update notification created but email may not have been sent for user: {enrollment.user.username}")
                        
                except Exception as e:
                    logger.error(f"Error sending conference update notification to {enrollment.user.username}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error processing conference update notifications: {str(e)}")
