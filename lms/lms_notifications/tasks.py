"""
Celery tasks for notification system
Handles scheduled notifications like deadline reminders
"""

from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_deadline_reminders():
    """
    Send deadline reminders for assignments due soon
    Runs daily to check for assignments due in 24-48 hours
    """
    try:
        from assignments.models import Assignment, AssignmentSubmission
        from courses.models import CourseEnrollment
        from lms_notifications.utils import send_notification
        
        now = timezone.now()
        tomorrow = now + timedelta(days=1)
        day_after = now + timedelta(days=2)
        
        # Get all active assignments due in the next 24-48 hours
        upcoming_assignments = Assignment.objects.filter(
            due_date__gte=tomorrow,
            due_date__lt=day_after,
            is_active=True
        ).select_related('course').prefetch_related('courses')
        
        reminder_count = 0
        
        for assignment in upcoming_assignments:
            # Get enrolled students for this assignment's course(s)
            if assignment.course:
                enrolled_users = CourseEnrollment.objects.filter(
                    course=assignment.course,
                    user__is_active=True
                ).values_list('user', flat=True)
            elif assignment.courses.exists():
                enrolled_users = CourseEnrollment.objects.filter(
                    course__in=assignment.courses.all(),
                    user__is_active=True
                ).values_list('user', flat=True).distinct()
            else:
                continue
            
            # Check each enrolled user
            for user_id in enrolled_users:
                # Check if user has already submitted
                has_submitted = AssignmentSubmission.objects.filter(
                    assignment=assignment,
                    user_id=user_id,
                    status__in=['submitted', 'graded']
                ).exists()
                
                if not has_submitted:
                    # Check if reminder was already sent today
                    from lms_notifications.models import Notification
                    reminder_sent_today = Notification.objects.filter(
                        recipient_id=user_id,
                        notification_type__name='deadline_reminder',
                        related_assignment=assignment,
                        created_at__date=now.date()
                    ).exists()
                    
                    if not reminder_sent_today:
                        try:
                            from django.contrib.auth import get_user_model
                            User = get_user_model()
                            user = User.objects.get(id=user_id)
                            
                            # Calculate time until deadline
                            hours_until = int((assignment.due_date - now).total_seconds() / 3600)
                            
                            # Send reminder notification
                            message = f"""
                            <h2>Assignment Deadline Reminder</h2>
                            <p>Dear {user.first_name or user.username},</p>
                            <p>This is a reminder that the following assignment is due soon:</p>
                            <p><strong>Assignment Details:</strong></p>
                            <ul>
                                <li><strong>Assignment:</strong> {assignment.title}</li>
                                <li><strong>Course:</strong> {assignment.course.title if assignment.course else 'Multiple Courses'}</li>
                                <li><strong>Due Date:</strong> {assignment.due_date.strftime('%B %d, %Y at %I:%M %p')}</li>
                                <li><strong>Time Remaining:</strong> Approximately {hours_until} hours</li>
                            </ul>
                            <p>Please make sure to complete and submit your assignment before the deadline.</p>
                            <p>Good luck!</p>
                            <p>Best regards,<br>The LMS Team</p>
                            """
                            
                            notification = send_notification(
                                recipient=user,
                                notification_type_name='deadline_reminder',
                                title=f"Deadline Reminder: {assignment.title}",
                                message=message,
                                short_message=f"Reminder: '{assignment.title}' is due in {hours_until} hours",
                                priority='high',
                                action_url=f"/assignments/{assignment.id}/",
                                action_text="View Assignment",
                                related_assignment=assignment,
                                send_email=True
                            )
                            
                            if notification:
                                reminder_count += 1
                                logger.info(f"Deadline reminder sent to {user.username} for assignment: {assignment.title}")
                                
                        except Exception as e:
                            logger.error(f"Error sending deadline reminder to user {user_id} for assignment {assignment.id}: {str(e)}")
        
        logger.info(f"Sent {reminder_count} deadline reminder notifications")
        return reminder_count
        
    except Exception as e:
        logger.error(f"Error in send_deadline_reminders task: {str(e)}")
        return 0


@shared_task
def send_unread_message_digest():
    """
    Send digest of unread messages to users
    Runs daily to remind users of unread messages
    """
    try:
        from django.contrib.auth import get_user_model
        from lms_messages.models import Message, MessageReadStatus
        from lms_notifications.utils import send_notification
        
        User = get_user_model()
        digest_count = 0
        
        # Get all active users
        active_users = User.objects.filter(is_active=True)
        
        for user in active_users:
            # Get unread messages for this user
            unread_messages = Message.objects.filter(
                recipients=user
            ).exclude(
                messagereadstatus__user=user,
                messagereadstatus__is_read=True
            ).order_by('-created_at')
            
            unread_count = unread_messages.count()
            
            if unread_count > 0:
                # Check if digest was already sent today
                from lms_notifications.models import Notification
                now = timezone.now()
                digest_sent_today = Notification.objects.filter(
                    recipient=user,
                    notification_type__name='message_unread',
                    created_at__date=now.date()
                ).exists()
                
                if not digest_sent_today:
                    try:
                        # Build message list
                        message_list = ""
                        for msg in unread_messages[:5]:  # Show up to 5 messages
                            sender_name = msg.sender.get_full_name() if msg.sender else "System"
                            message_list += f"<li><strong>From {sender_name}:</strong> {msg.subject}</li>"
                        
                        if unread_count > 5:
                            message_list += f"<li><em>...and {unread_count - 5} more messages</em></li>"
                        
                        # Send digest notification
                        digest_message = f"""
                        <h2>Unread Messages Summary</h2>
                        <p>Dear {user.first_name or user.username},</p>
                        <p>You have <strong>{unread_count}</strong> unread message{'s' if unread_count != 1 else ''} in your inbox:</p>
                        <ul>
                        {message_list}
                        </ul>
                        <p>Please log in to your account to read and respond to your messages.</p>
                        <p>Best regards,<br>The LMS Team</p>
                        """
                        
                        notification = send_notification(
                            recipient=user,
                            notification_type_name='message_unread',
                            title=f"You have {unread_count} unread message{'s' if unread_count != 1 else ''}",
                            message=digest_message,
                            short_message=f"You have {unread_count} unread message{'s' if unread_count != 1 else ''} in your inbox",
                            priority='normal',
                            action_url="/messages/",
                            action_text="View Messages",
                            send_email=True
                        )
                        
                        if notification:
                            digest_count += 1
                            logger.info(f"Message digest sent to {user.username} ({unread_count} unread messages)")
                            
                    except Exception as e:
                        logger.error(f"Error sending message digest to {user.username}: {str(e)}")
        
        logger.info(f"Sent {digest_count} message digest notifications")
        return digest_count
        
    except Exception as e:
        logger.error(f"Error in send_unread_message_digest task: {str(e)}")
        return 0


@shared_task
def send_feedback_reminders():
    """
    Send reminders to view feedback on graded assignments
    Runs daily to check for graded assignments with unviewed feedback
    """
    try:
        from assignments.models import AssignmentSubmission
        from lms_notifications.utils import send_notification
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        now = timezone.now()
        three_days_ago = now - timedelta(days=3)
        
        # Get graded submissions with feedback from the last 3 days
        graded_submissions = AssignmentSubmission.objects.filter(
            status='graded',
            grade__isnull=False,
            graded_at__gte=three_days_ago,
            graded_at__lte=now
        ).exclude(
            Q(feedback='') | Q(feedback__isnull=True)
        ).select_related('assignment', 'assignment__course', 'user')
        
        reminder_count = 0
        
        for submission in graded_submissions:
            # Check if feedback reminder was already sent
            from lms_notifications.models import Notification
            reminder_sent = Notification.objects.filter(
                recipient=submission.user,
                notification_type__name='feedback_available',
                related_assignment=submission.assignment,
                created_at__gte=submission.graded_at
            ).exists()
            
            if not reminder_sent:
                try:
                    # Calculate grade percentage
                    grade_pct = (submission.grade / submission.assignment.points * 100) if submission.assignment.points else 0
                    
                    # Send feedback reminder
                    message = f"""
                    <h2>Assignment Feedback Available</h2>
                    <p>Dear {submission.user.first_name or submission.user.username},</p>
                    <p>Your assignment has been graded and feedback is available for review:</p>
                    <p><strong>Assignment Details:</strong></p>
                    <ul>
                        <li><strong>Assignment:</strong> {submission.assignment.title}</li>
                        <li><strong>Course:</strong> {submission.assignment.course.title if submission.assignment.course else 'General'}</li>
                        <li><strong>Grade:</strong> {submission.grade} / {submission.assignment.points}</li>
                        <li><strong>Percentage:</strong> {grade_pct:.1f}%</li>
                        <li><strong>Graded At:</strong> {submission.graded_at.strftime('%B %d, %Y at %I:%M %p')}</li>
                    </ul>
                    <p>Your instructor has provided feedback on your submission. Please review it to improve your future work.</p>
                    <p>Keep up the good work!</p>
                    <p>Best regards,<br>The LMS Team</p>
                    """
                    
                    notification = send_notification(
                        recipient=submission.user,
                        notification_type_name='feedback_available',
                        title=f"Feedback Available: {submission.assignment.title}",
                        message=message,
                        short_message=f"Your assignment '{submission.assignment.title}' has been graded with feedback",
                        priority='normal',
                        action_url=f"/assignments/{submission.assignment.id}/submission/{submission.id}/",
                        action_text="View Feedback",
                        related_assignment=submission.assignment,
                        send_email=True
                    )
                    
                    if notification:
                        reminder_count += 1
                        logger.info(f"Feedback reminder sent to {submission.user.username} for assignment: {submission.assignment.title}")
                        
                except Exception as e:
                    logger.error(f"Error sending feedback reminder to {submission.user.username} for assignment {submission.assignment.id}: {str(e)}")
        
        logger.info(f"Sent {reminder_count} feedback reminder notifications")
        return reminder_count
        
    except Exception as e:
        logger.error(f"Error in send_feedback_reminders task: {str(e)}")
        return 0

