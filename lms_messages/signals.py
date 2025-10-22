"""
Message-related signals for email notifications
Handles notifications when users receive new messages
"""

from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.urls import reverse
import logging

from .models import Message

logger = logging.getLogger(__name__)


@receiver(m2m_changed, sender=Message.recipients.through)
def send_message_notification(sender, instance, action, pk_set, **kwargs):
    """
    Send email notification when a user receives a new message
    This signal is triggered when recipients are added to a message
    """
    if action == "post_add" and pk_set:
        try:
            # Import here to avoid circular imports
            from lms_notifications.utils import send_notification
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            # Get all recipients that were just added
            recipients = User.objects.filter(pk__in=pk_set)
            
            for recipient in recipients:
                try:
                    # Prepare message notification
                    message_content = f"""
                    <h2>New Message Received</h2>
                    <p>Dear {recipient.first_name or recipient.username},</p>
                    <p>You have received a new message:</p>
                    <p><strong>From:</strong> {instance.sender.get_full_name() or instance.sender.username}</p>
                    <p><strong>Subject:</strong> {instance.subject}</p>
                    <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #2196F3; margin: 15px 0;">
                        <p><strong>Message Preview:</strong></p>
                        <p>{instance.content[:200]}...</p>
                    </div>
                    <p>Please log in to your account to read and respond to this message.</p>
                    <p>Best regards,<br>The LMS Team</p>
                    """
                    
                    # Send notification
                    notification = send_notification(
                        recipient=recipient,
                        notification_type_name='message_received',
                        title=f"New Message: {instance.subject}",
                        message=message_content,
                        short_message=f"You have a new message from {instance.sender.get_full_name() or instance.sender.username}",
                        sender=instance.sender,
                        priority='normal',
                        action_url=f"/messages/{instance.id}/",
                        action_text="Read Message",
                        send_email=True
                    )
                    
                    if notification:
                        logger.info(f"Message notification sent to user: {recipient.username} from {instance.sender.username}")
                    else:
                        logger.warning(f"Message notification created but email may not have been sent for user: {recipient.username}")
                        
                except Exception as e:
                    logger.error(f"Error sending message notification to {recipient.username}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error processing message notification: {str(e)}")

