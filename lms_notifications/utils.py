from django.contrib.auth import get_user_model
from django.utils import timezone
import logging
from .models import Notification, NotificationType, BulkNotification, NotificationLog

logger = logging.getLogger(__name__)

User = get_user_model()


def send_notification(
    recipient,
    notification_type_name,
    title,
    message,
    short_message=None,
    sender=None,
    priority='normal',
    action_url=None,
    action_text=None,
    related_course=None,
    related_assignment=None,
    context_data=None,
    send_email=True
):
    """
    Send a notification to a single user.
    
    Args:
        recipient: User object or user ID
        notification_type_name: String name of the notification type
        title: Notification title
        message: Full notification message (HTML supported)
        short_message: Brief version for previews (optional)
        sender: User object who sent the notification (optional)
        priority: 'low', 'normal', 'high', 'urgent'
        action_url: URL for action button (optional)
        action_text: Text for action button (optional)
        related_course: Course object (optional)
        related_assignment: Assignment object (optional)
        context_data: Additional context data (dict, optional)
        send_email: Whether to attempt email sending (default: True)
    
    Returns:
        Notification object if successful, None if failed
    """
    try:
        # Get recipient user object
        if isinstance(recipient, int):
            recipient = User.objects.get(id=recipient)
        
        # Get notification type
        try:
            notification_type = NotificationType.objects.get(
                name=notification_type_name,
                is_active=True
            )
        except NotificationType.DoesNotExist:
            logger.warning(f"Warning: Notification type '{notification_type_name}' not found")
            return None
        
        # Check if user can receive this notification type
        if (notification_type.available_to_roles and 
            recipient.role not in notification_type.available_to_roles):
            logger.warning(f"Warning: User {recipient.username} cannot receive {notification_type_name} notifications")
            return None
        
        # Set short message if not provided
        if not short_message:
            # Strip HTML and truncate
            import re
            clean_message = re.sub('<.*?>', '', message)
            short_message = clean_message[:200] + '...' if len(clean_message) > 200 else clean_message
        
        # Create notification
        notification = Notification.objects.create(
            notification_type=notification_type,
            recipient=recipient,
            sender=sender,
            title=title,
            message=message,
            short_message=short_message,
            priority=priority,
            action_url=action_url or '',
            action_text=action_text or '',
            related_course=related_course,
            related_assignment=related_assignment,
            context_data=context_data or {}
        )
        
        # Log creation
        NotificationLog.objects.create(
            notification=notification,
            action='created',
            user=sender or recipient,
            details={'send_email': send_email}
        )
        
        # Send email if requested
        if send_email:
            try:
                email_sent = notification.send_email()
                if email_sent:
                    NotificationLog.objects.create(
                        notification=notification,
                        action='email_sent',
                        user=recipient
                    )
                else:
                    NotificationLog.objects.create(
                        notification=notification,
                        action='email_failed',
                        user=recipient,
                        details={'reason': 'User settings'}
                    )
            except Exception as e:
                NotificationLog.objects.create(
                    notification=notification,
                    action='email_failed',
                    user=recipient,
                    details={'error': str(e)}
                )
        
        return notification
        
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        return None


def send_bulk_notification(
    sender,
    notification_type_name,
    title,
    message,
    short_message=None,
    recipient_type='all_users',
    target_roles=None,
    target_branches=None,
    target_groups=None,
    target_courses=None,
    custom_recipients=None,
    priority='normal',
    action_url=None,
    action_text=None,
    scheduled_for=None
):
    """
    Send a bulk notification to multiple users.
    
    Args:
        sender: User object sending the notification
        notification_type_name: String name of the notification type
        title: Notification title
        message: Full notification message (HTML supported)
        short_message: Brief version for previews (optional)
        recipient_type: 'all_users', 'role', 'branch', 'group', 'course', 'custom'
        target_roles: List of role names (for recipient_type='role')
        target_branches: List of Branch objects (for recipient_type='branch')
        target_groups: List of BranchGroup objects (for recipient_type='group')
        target_courses: List of Course objects (for recipient_type='course')
        custom_recipients: List of User objects (for recipient_type='custom')
        priority: 'low', 'normal', 'high', 'urgent'
        action_url: URL for action button (optional)
        action_text: Text for action button (optional)
        scheduled_for: DateTime to send (optional, sends immediately if None)
    
    Returns:
        BulkNotification object if successful, None if failed
    """
    try:
        # Get notification type
        try:
            notification_type = NotificationType.objects.get(
                name=notification_type_name,
                is_active=True
            )
        except NotificationType.DoesNotExist:
            logger.warning(f"Warning: Notification type '{notification_type_name}' not found")
            return None
        
        # Set short message if not provided
        if not short_message:
            import re
            clean_message = re.sub('<.*?>', '', message)
            short_message = clean_message[:200] + '...' if len(clean_message) > 200 else clean_message
        
        # Create bulk notification
        bulk_notification = BulkNotification.objects.create(
            title=title,
            message=message,
            short_message=short_message,
            notification_type=notification_type,
            sender=sender,
            recipient_type=recipient_type,
            target_roles=target_roles or [],
            priority=priority,
            action_url=action_url or '',
            action_text=action_text or '',
            scheduled_for=scheduled_for
        )
        
        # Set many-to-many relationships
        if target_branches:
            bulk_notification.target_branches.set(target_branches)
        if target_groups:
            bulk_notification.target_groups.set(target_groups)
        if target_courses:
            bulk_notification.target_courses.set(target_courses)
        if custom_recipients:
            bulk_notification.custom_recipients.set(custom_recipients)
        
        # Send immediately if not scheduled
        if not scheduled_for:
            result = bulk_notification.send_notifications()
            if result:
                NotificationLog.objects.create(
                    bulk_notification=bulk_notification,
                    action='bulk_sent',
                    user=sender,
                    details={'total_recipients': bulk_notification.total_recipients}
                )
        
        return bulk_notification
        
    except Exception as e:
        logger.error(f"Error sending bulk notification: {str(e)}")
        return None


def get_user_notification_count(user):
    """
    Get notification counts for a user.
    
    Returns:
        dict with 'total', 'unread', 'urgent', 'high' counts
    """
    notifications = Notification.objects.filter(recipient=user)
    
    return {
        'total': notifications.count(),
        'unread': notifications.filter(is_read=False).count(),
        'urgent': notifications.filter(priority='urgent', is_read=False).count(),
        'high': notifications.filter(priority='high', is_read=False).count(),
    }


def mark_notifications_read(user, notification_ids=None):
    """
    Mark notifications as read for a user.
    
    Args:
        user: User object
        notification_ids: List of notification IDs (optional, marks all if None)
    
    Returns:
        Number of notifications marked as read
    """
    notifications = Notification.objects.filter(recipient=user, is_read=False)
    
    if notification_ids:
        notifications = notifications.filter(id__in=notification_ids)
    
    count = notifications.update(is_read=True, read_at=timezone.now())
    
    # Log the action for each notification
    for notification in notifications:
        NotificationLog.objects.create(
            notification=notification,
            action='read',
            user=user
        )
    
    return count


def delete_notifications(user, notification_ids):
    """
    Delete specific notifications for a user.
    
    Args:
        user: User object
        notification_ids: List of notification IDs to delete
    
    Returns:
        Number of notifications deleted
    """
    notifications = Notification.objects.filter(recipient=user, id__in=notification_ids)
    
    # Log deletions
    for notification in notifications:
        NotificationLog.objects.create(
            notification=notification,
            action='deleted',
            user=user
        )
    
    count, _ = notifications.delete()
    return count


# Convenience functions for common notification types

def notify_assignment_due(assignment, recipient, days_until_due=1):
    """Send assignment due reminder notification."""
    # Validation: Ensure assignment exists and has required fields
    if not assignment or not assignment.id:
        logger.warning(f"Warning: Cannot create notification for invalid assignment: {assignment}")
        return None
    
    if not assignment.title:
        logger.warning(f"Warning: Assignment {assignment.id} has no title")
        return None
    
    return send_notification(
        recipient=recipient,
        notification_type_name='assignment_due',
        title=f"Assignment Due: {assignment.title}",
        message=f"Your assignment <strong>{assignment.title}</strong> is due in {days_until_due} day{'s' if days_until_due != 1 else ''}.",
        priority='high' if days_until_due <= 1 else 'normal',
        action_url=f"/assignments/{assignment.id}/",
        action_text="View Assignment",
        related_assignment=assignment,
        related_course=assignment.course if hasattr(assignment, 'course') else None
    )


def notify_assignment_graded(assignment, recipient, grade=None):
    """Send assignment graded notification."""
    # Validation: Ensure assignment exists and has required fields
    if not assignment or not assignment.id:
        logger.warning(f"Warning: Cannot create graded notification for invalid assignment: {assignment}")
        return None
    
    if not assignment.title:
        logger.warning(f"Warning: Assignment {assignment.id} has no title")
        return None
    
    message = f"Your assignment <strong>{assignment.title}</strong> has been graded."
    if grade:
        message += f" You received a grade of {grade}."
    
    return send_notification(
        recipient=recipient,
        notification_type_name='assignment_graded',
        title=f"Assignment Graded: {assignment.title}",
        message=message,
        priority='normal',
        action_url=f"/assignments/{assignment.id}/",
        action_text="View Grade",
        related_assignment=assignment,
        related_course=assignment.course if hasattr(assignment, 'course') else None
    )


def notify_course_enrollment(course, recipient, sender=None):
    """Send course enrollment notification."""
    return send_notification(
        recipient=recipient,
        notification_type_name='course_enrollment',
        title=f"Enrolled in {course.title}",
        message=f"You have been successfully enrolled in <strong>{course.title}</strong>.",
        sender=sender,
        priority='normal',
        action_url=f"/courses/{course.id}/",
        action_text="View Course",
        related_course=course
    )


def notify_course_announcement(course, recipients, announcement_title, announcement_content, sender):
    """Send course announcement to multiple recipients."""
    return send_bulk_notification(
        sender=sender,
        notification_type_name='course_announcement',
        title=f"Course Announcement: {announcement_title}",
        message=announcement_content,
        recipient_type='custom',
        custom_recipients=recipients,
        priority='normal',
        action_url=f"/courses/{course.id}/",
        action_text="View Course"
    )


def notify_system_maintenance(title, message, start_time, end_time, sender):
    """Send system maintenance notification to all users."""
    full_message = f"{message}<br><br><strong>Maintenance Window:</strong> {start_time} - {end_time}"
    
    return send_bulk_notification(
        sender=sender,
        notification_type_name='system_maintenance',
        title=title,
        message=full_message,
        recipient_type='all_users',
        priority='high'
    ) 