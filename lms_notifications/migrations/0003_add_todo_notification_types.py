# Generated migration for adding todo-related notification types
from django.db import migrations

def add_todo_notification_types(apps, schema_editor):
    """Add notification types for todo list items"""
    NotificationType = apps.get_model('lms_notifications', 'NotificationType')
    
    notification_types = [
        {
            'name': 'feedback_available',
            'display_name': 'Assignment Feedback Available',
            'description': 'Notification when your assignment has been graded with feedback',
            'is_active': True,
            'can_be_disabled': True,
            'available_to_roles': ['learner'],
            'default_email_enabled': True,
            'default_web_enabled': True,
        },
        {
            'name': 'message_unread',
            'display_name': 'Unread Messages',
            'description': 'Notification for unread messages in your inbox',
            'is_active': True,
            'can_be_disabled': True,
            'available_to_roles': ['learner', 'instructor', 'admin', 'superadmin'],
            'default_email_enabled': True,
            'default_web_enabled': True,
        },
        {
            'name': 'deadline_reminder',
            'display_name': 'Upcoming Deadline Reminder',
            'description': 'Reminder notification for assignments due soon',
            'is_active': True,
            'can_be_disabled': True,
            'available_to_roles': ['learner'],
            'default_email_enabled': True,
            'default_web_enabled': True,
        },
        {
            'name': 'conference_scheduled',
            'display_name': 'Conference Scheduled',
            'description': 'Notification when a new conference is scheduled',
            'is_active': True,
            'can_be_disabled': True,
            'available_to_roles': ['learner', 'instructor'],
            'default_email_enabled': True,
            'default_web_enabled': True,
        },
    ]
    
    for type_data in notification_types:
        NotificationType.objects.get_or_create(
            name=type_data['name'],
            defaults=type_data
        )

def remove_todo_notification_types(apps, schema_editor):
    """Remove todo-related notification types"""
    NotificationType = apps.get_model('lms_notifications', 'NotificationType')
    
    notification_type_names = [
        'feedback_available',
        'message_unread',
        'deadline_reminder',
        'conference_scheduled',
    ]
    
    NotificationType.objects.filter(name__in=notification_type_names).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('lms_notifications', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(add_todo_notification_types, remove_todo_notification_types),
    ]

