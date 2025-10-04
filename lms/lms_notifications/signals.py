from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from django.conf import settings
import logging
from .models import NotificationType, NotificationSettings

logger = logging.getLogger(__name__)


@receiver(post_migrate)
def create_default_notification_types(sender, **kwargs):
    """Create default notification types after migration"""
    if sender.name == 'lms_notifications':
        # Check if the NotificationType table exists before trying to access it
        from django.db import connection
        table_name = NotificationType._meta.db_table
        if table_name not in connection.introspection.table_names():
            return  # Table doesn't exist yet, skip signal
        
        default_types = [
            {
                'name': 'account_Session',
                'display_name': 'Account Session',
                'description': 'Session-related notifications for your account',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin'],
                'default_email_enabled': True,
                'default_web_enabled': True,
                'can_be_disabled': False,
                'is_active': True,
            },
            {
                'name': 'welcome_mail',
                'display_name': 'Welcome Mail',
                'description': 'Welcome email sent to new users upon account creation',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
                'can_be_disabled': False,
                'is_active': True,
            },
            {
                'name': 'assignment_due',
                'display_name': 'Assignment Due',
                'description': 'Reminders about upcoming assignment deadlines',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
                'is_active': True,
            },
            {
                'name': 'assignment_graded',
                'display_name': 'Assignment Graded',
                'description': 'Notifications when assignments are graded',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
                'is_active': True,
            },
            {
                'name': 'bulk_announcement',
                'display_name': 'Bulk Announcement',
                'description': 'Mass announcements from administrators and instructors',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor'],
                'default_email_enabled': True,
                'default_web_enabled': True,
                'can_be_disabled': False,
                'is_active': True,
            },
            {
                'name': 'certificate_earned',
                'display_name': 'Certificate Earned',
                'description': 'Notifications about earned certificates and achievements',
                'available_to_roles': ['learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'conference_reminder',
                'display_name': 'Conference Reminder',
                'description': 'Reminders about upcoming conferences and meetings',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'course_announcement',
                'display_name': 'Course Announcement',
                'description': 'Important announcements from course instructors',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'course_completion',
                'display_name': 'Course Completion',
                'description': 'Congratulations on completing courses',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'course_enrollment',
                'display_name': 'Course Enrollment',
                'description': 'Notifications about course enrollments and registrations',
                'available_to_roles': ['learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'deadline_reminder',
                'display_name': 'Deadline Reminder',
                'description': 'General deadline reminders for various activities',
                'available_to_roles': ['learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'discussion_reply',
                'display_name': 'Discussion Reply',
                'description': 'Notifications about replies to your discussion posts',
                'available_to_roles': ['learner'],
                'default_email_enabled': False,
                'default_web_enabled': True,
            },
            {
                'name': 'enrollment_approved',
                'display_name': 'Enrollment Approved',
                'description': 'Notifications when course enrollment requests are approved',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'enrollment_rejected',
                'display_name': 'Enrollment Rejected',
                'description': 'Notifications when course enrollment requests are rejected',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'instructor_feedback',
                'display_name': 'Instructor Feedback',
                'description': 'Personal feedback from instructors',
                'available_to_roles': ['learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'message_received',
                'display_name': 'Message Received',
                'description': 'Notifications about new private messages',
                'available_to_roles': ['learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'quiz_available',
                'display_name': 'Quiz Available',
                'description': 'Notifications about new quizzes and assessments',
                'available_to_roles': ['learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'quiz_reminder',
                'display_name': 'Quiz Reminder',
                'description': 'Reminders about upcoming quiz deadlines',
                'available_to_roles': ['learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'report_ready',
                'display_name': 'Report Ready',
                'description': 'Notifications when requested reports are ready',
                'available_to_roles': ['learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
            },
            {
                'name': 'system_maintenance',
                'display_name': 'System Maintenance',
                'description': 'Important system updates and maintenance notifications',
                'available_to_roles': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner'],
                'default_email_enabled': True,
                'default_web_enabled': True,
                'can_be_disabled': False,
                'is_active': True,
            },
        ]
        
        try:
            for type_data in default_types:
                NotificationType.objects.get_or_create(
                    name=type_data['name'],
                    defaults=type_data
                )
        except Exception as e:
            # If there's any database error, silently continue
            # This prevents migration failures due to database inconsistencies
            logger.warning(f"Could not create default notification types: {e}")
            return


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_notification_settings(sender, instance, created, **kwargs):
    """Create default notification settings for new users"""
    if created:
        NotificationSettings.objects.get_or_create(
            user=instance,
            defaults={
                'email_notifications_enabled': True,
                'web_notifications_enabled': True,
                'daily_digest_enabled': False,
                'weekly_digest_enabled': True,
            }
        ) 