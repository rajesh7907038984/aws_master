"""
User-related signals for email notifications
Handles welcome emails and user account notifications
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.urls import reverse
import logging

from .models import CustomUser

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CustomUser)
def send_welcome_email(sender, instance, created, **kwargs):
    """
    Send welcome email when a new user is created
    """
    if created and instance.email:
        try:
            # Import here to avoid circular imports
            from lms_notifications.utils import send_notification
            
            # Prepare welcome message
            welcome_message = f"""
            <h2>Welcome to our Learning Management System!</h2>
            <p>Dear {instance.first_name or instance.username},</p>
            <p>Your account has been successfully created. We're excited to have you join our learning community!</p>
            <p><strong>Account Details:</strong></p>
            <ul>
                <li>Username: {instance.username}</li>
                <li>Email: {instance.email}</li>
                <li>Role: {instance.get_role_display()}</li>
                {f'<li>Branch: {instance.branch.name}</li>' if instance.branch else ''}
            </ul>
            <p>You can now log in and start exploring the platform.</p>
            <p>If you have any questions, please don't hesitate to contact our support team.</p>
            <p>Best regards,<br>The LMS Team</p>
            """
            
            # Send notification
            notification = send_notification(
                recipient=instance,
                notification_type_name='welcome_mail',
                title=f"Welcome to LMS, {instance.first_name or instance.username}!",
                message=welcome_message,
                short_message=f"Welcome to our Learning Management System! Your account has been successfully created.",
                priority='normal',
                action_url=reverse('users:role_based_redirect'),
                action_text="Go to Dashboard",
                send_email=True
            )
            
            if notification:
                logger.info(f"Welcome email sent to new user: {instance.username}")
            else:
                logger.warning(f"Welcome notification created but email may not have been sent for user: {instance.username}")
                
        except Exception as e:
            logger.error(f"Error sending welcome email to {instance.username}: {str(e)}")

