from django.db import models
from django.conf import settings
from django.utils import timezone
from core.utils.fields import TinyMCEField
from users.models import Branch
from groups.models import BranchGroup
from core.s3_storage import MediaS3Storage

class Message(models.Model):
    """Model for storing messages"""
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='received_messages'
    )
    subject = models.CharField(max_length=255)
    content = TinyMCEField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Reply threading
    parent_message = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        help_text="The message this is a reply to"
    )
    external_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="ID from external message source"
    )
    external_source = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Source of external message"
    )
    # New fields for group messaging
    sent_to_group = models.ForeignKey(
        BranchGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_messages',
        help_text="Group this message was sent to (if applicable)"
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='branch_messages',
        help_text="Branch associated with this message"
    )
    is_course_message = models.BooleanField(
        default=False,
        help_text="Whether this message is related to a specific course"
    )
    related_course = models.ForeignKey(
        'courses.Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='course_messages',
        help_text="The course this message is related to (if applicable)"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['external_id']),
            models.Index(fields=['branch']),
            models.Index(fields=['sent_to_group']),
            models.Index(fields=['related_course']),
        ]

    def __str__(self):
        return f"{self.subject} - From: {self.sender.username}"

    def mark_read(self, user):
        """Mark message as read for a specific user"""
        from lms_messages.models import MessageReadStatus
        status, created = MessageReadStatus.objects.get_or_create(
            message=self,
            user=user,
            defaults={'is_read': True}
        )
        if not created and not status.is_read:
            status.is_read = True
            status.read_at = timezone.now()
            status.save()
        return status
    
    @property
    def read_count(self):
        """Count how many recipients have read the message"""
        return self.read_statuses.filter(is_read=True).count()
    
    @property
    def unread_count(self):
        """Count how many recipients haven't read the message"""
        return self.recipients.count() - self.read_count

class MessageReadStatus(models.Model):
    """Track read status per user for each message"""
    message = models.ForeignKey(
        Message, 
        on_delete=models.CASCADE,
        related_name='read_statuses'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_read_statuses'
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['message', 'user']
        indexes = [
            models.Index(fields=['message', 'user']),
            models.Index(fields=['user', 'is_read']),
        ]
        
    def __str__(self):
        status = "Read" if self.is_read else "Unread"
        return f"{self.message.subject} - {self.user.username} - {status}"

class MessageAttachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='message_attachments/%Y/%m/%d/', storage=MediaS3Storage())
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']
        indexes = [
            models.Index(fields=['message', 'uploaded_at']),
        ]

    def __str__(self):
        return self.filename

    def delete(self, *args, **kwargs):
        """Enhanced delete method with S3 cleanup for message attachments."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Starting deletion for MessageAttachment: {self.filename} (ID: {self.id})")
            
            # Delete attachment file
            if self.file:
                try:
                    self.file.delete(save=False)
                    logger.info(f"Deleted message attachment: {self.file.name}")
                except Exception as e:
                    logger.error(f"Error deleting message attachment: {e}")
            
            # S3 cleanup
            try:
                from core.utils.s3_cleanup import cleanup_message_s3_files
                s3_results = cleanup_message_s3_files(self.id)
                successful_s3_deletions = sum(1 for success in s3_results.values() if success)
                total_s3_files = len(s3_results)
                if total_s3_files > 0:
                    logger.info(f"S3 cleanup: {successful_s3_deletions}/{total_s3_files} message attachment files deleted successfully")
            except Exception as e:
                logger.error(f"Error during S3 cleanup for message attachment {self.id}: {str(e)}")
            
            # Call parent delete to remove the database record
            super().delete(*args, **kwargs)
            logger.info(f"Successfully completed deletion for MessageAttachment: {self.filename} (ID: {self.id})")
            
        except Exception as e:
            logger.error(f"Error in MessageAttachment.delete(): {str(e)}")
            raise
