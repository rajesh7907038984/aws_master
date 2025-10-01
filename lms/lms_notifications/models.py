from django.db import models
from django.conf import settings
from django.utils import timezone
from core.utils.fields import TinyMCEField
from users.models import Branch
from groups.models import BranchGroup
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.smtp import EmailBackend
from django.core.mail import EmailMessage


class NotificationType(models.Model):
    """
    Define different types of notifications in the system
    """
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    can_be_disabled = models.BooleanField(default=True, help_text="Whether users can disable this notification type")
    
    # Role-based access
    available_to_roles = models.JSONField(
        default=list,
        help_text="List of roles that can receive this notification type (empty = all roles)"
    )
    
    # Default settings
    default_email_enabled = models.BooleanField(default=True)
    default_web_enabled = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Use primary key ordering to avoid potential column issues during deletion
        ordering = ['id']
        indexes = [
            models.Index(fields=['name', 'is_active']),
        ]

    def __str__(self):
        return self.display_name


class NotificationSettings(models.Model):
    """
    User-specific notification preferences
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_settings'
    )
    
    # Global settings
    email_notifications_enabled = models.BooleanField(default=True)
    web_notifications_enabled = models.BooleanField(default=True)
    
    # Digest settings
    daily_digest_enabled = models.BooleanField(default=False)
    weekly_digest_enabled = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"Notification settings for {self.user.username}"


class NotificationTypeSettings(models.Model):
    """
    User-specific settings for each notification type
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_type_settings'
    )
    notification_type = models.ForeignKey(
        NotificationType,
        on_delete=models.CASCADE,
        related_name='user_settings'
    )
    
    email_enabled = models.BooleanField(default=True)
    web_enabled = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'notification_type']
        indexes = [
            models.Index(fields=['user', 'notification_type']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.notification_type.display_name}"


class Notification(models.Model):
    """
    Individual notification instance
    """
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    notification_type = models.ForeignKey(
        NotificationType,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    
    # Recipients
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_notifications'
    )
    
    # Sender (optional, for system notifications it can be null)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )
    
    # Content
    title = models.CharField(max_length=255)
    message = TinyMCEField()
    short_message = models.CharField(
        max_length=500,
        help_text="Brief version for previews and mobile notifications"
    )
    
    # Priority and status
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Email status
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.TextField(blank=True)
    
    # Links and actions
    action_url = models.URLField(blank=True, help_text="URL to redirect when notification is clicked")
    action_text = models.CharField(max_length=100, blank=True, help_text="Text for action button")
    
    # Context data
    context_data = models.JSONField(default=dict, blank=True, help_text="Additional data for the notification")
    
    # Related objects
    related_course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    related_assignment = models.ForeignKey(
        'assignments.Assignment',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When this notification should expire")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['notification_type', '-created_at']),
            models.Index(fields=['priority', '-created_at']),
            models.Index(fields=['email_sent', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} - {self.recipient.username}"

    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def send_email(self):
        """Send email notification if enabled for user"""
        if self.email_sent:
            return False
            
        try:
            # Check if user has email notifications enabled
            settings_obj, _ = NotificationSettings.objects.get_or_create(user=self.recipient)
            
            if not settings_obj.email_notifications_enabled:
                return False
            
            # Check type-specific settings
            type_settings, _ = NotificationTypeSettings.objects.get_or_create(
                user=self.recipient,
                notification_type=self.notification_type,
                defaults={
                    'email_enabled': self.notification_type.default_email_enabled,
                    'web_enabled': self.notification_type.default_web_enabled,
                }
            )
            
            if not type_settings.email_enabled:
                return False
            

            
            # Prepare email content
            context = {
                'notification': self,
                'user': self.recipient,
                'site_name': 'LMS Platform',
                'action_url': self.get_absolute_action_url(),
            }
            
            subject = f"[LMS] {self.title}"
            
            # Use certificate template for certificate notifications
            if self.notification_type.name == 'certificate_earned':
                html_message = render_to_string('lms_notifications/email/certificate_notification.html', context)
            else:
                html_message = render_to_string('lms_notifications/email/notification.html', context)
            
            text_message = render_to_string('lms_notifications/email/notification.txt', context)
            
            # Use OAuth2 backend by default, fallback to SMTP if configured
            from_email = settings.DEFAULT_FROM_EMAIL
            email_backend = None
            reply_to_email = None
            
            # Check if OAuth2 backend is configured (preferred method)
            if hasattr(settings, 'EMAIL_BACKEND') and 'oauth2' in settings.EMAIL_BACKEND.lower():
                # Use OAuth2 backend with default settings
                from_email = getattr(settings, 'OUTLOOK_FROM_EMAIL', settings.DEFAULT_FROM_EMAIL)
                # Let Django use the default EMAIL_BACKEND (OAuth2)
                email_backend = None
            else:
                # Use Global Admin Settings for SMTP configuration
                try:
                    from account_settings.models import GlobalAdminSettings
                    global_settings = GlobalAdminSettings.get_settings()
                    
                    if global_settings.smtp_enabled and global_settings.smtp_host:
                        email_backend = global_settings.get_email_backend()
                        from_email = global_settings.get_from_email() or settings.DEFAULT_FROM_EMAIL
                        reply_to_email = global_settings.smtp_reply_to_email
                    else:
                        # Global Admin Settings not configured - cannot send email
                        raise Exception("Email configuration not found. Please configure SMTP settings via Global Admin Settings.")
                except Exception as e:
                    # Re-raise the exception with a clear message
                    raise Exception(f"Email configuration error: {str(e)}. Please configure SMTP settings via Global Admin Settings.")
            
            # Create email message
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=from_email,
                to=[self.recipient.email],
                connection=email_backend
            )
            email.attach_alternative(html_message, "text/html")
            
            # Add reply-to if specified
            if reply_to_email:
                email.reply_to = [reply_to_email]
            
            # Send email
            email.send(fail_silently=False)
            
            self.email_sent = True
            self.email_sent_at = timezone.now()
            self.save(update_fields=['email_sent', 'email_sent_at'])
            
            return True
            
        except Exception as e:
            self.email_error = str(e)
            self.save(update_fields=['email_error'])
            return False

    def get_absolute_action_url(self):
        """Get full URL for action"""
        if self.action_url:
            if self.action_url.startswith('http'):
                return self.action_url
            else:
                from django.contrib.sites.models import Site
                current_site = Site.objects.get_current()
                return f"https://{current_site.domain}{self.action_url}"
        return None


class BulkNotification(models.Model):
    """
    For sending notifications to multiple users at once
    """
    RECIPIENT_TYPE_CHOICES = [
        ('all_users', 'All Users'),
        ('role', 'By Role'),
        ('branch', 'By Branch'),
        ('group', 'By Group'),
        ('course', 'By Course'),
        ('custom', 'Custom List'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sending', 'Sending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    # Basic info
    title = models.CharField(max_length=255)
    message = TinyMCEField()
    short_message = models.CharField(max_length=500)
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)
    
    # Sender
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bulk_notifications_sent'
    )
    
    # Recipients
    recipient_type = models.CharField(max_length=20, choices=RECIPIENT_TYPE_CHOICES)
    target_roles = models.JSONField(default=list, blank=True)
    target_branches = models.ManyToManyField(Branch, blank=True)
    target_groups = models.ManyToManyField(BranchGroup, blank=True)
    target_courses = models.ManyToManyField('courses.Course', blank=True)
    custom_recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='custom_bulk_notifications'
    )
    
    # Scheduling
    scheduled_for = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Stats
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    
    # Priority and links
    priority = models.CharField(max_length=10, choices=Notification.PRIORITY_CHOICES, default='normal')
    action_url = models.URLField(blank=True)
    action_text = models.CharField(max_length=100, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['scheduled_for']),
        ]

    def __str__(self):
        return f"Bulk: {self.title} ({self.status})"

    def get_recipients(self):
        """Get list of users who should receive this notification"""
        recipients = set()
        
        if self.recipient_type == 'all_users':
            from users.models import CustomUser
            recipients.update(CustomUser.objects.filter(is_active=True))
            
        elif self.recipient_type == 'role':
            from users.models import CustomUser
            if self.target_roles:
                recipients.update(CustomUser.objects.filter(
                    role__in=self.target_roles,
                    is_active=True
                ))
                
        elif self.recipient_type == 'branch':
            for branch in self.target_branches.all():
                recipients.update(branch.users.filter(is_active=True))
                
        elif self.recipient_type == 'group':
            for group in self.target_groups.all():
                recipients.update(group.students.filter(is_active=True))
                
        elif self.recipient_type == 'course':
            for course in self.target_courses.all():
                # Get enrolled students
                recipients.update(course.enrolled_students.filter(is_active=True))
                
        elif self.recipient_type == 'custom':
            recipients.update(self.custom_recipients.filter(is_active=True))
        
        return list(recipients)

    def send_notifications(self):
        """Send individual notifications to all recipients"""
        if self.status != 'draft' and self.status != 'scheduled':
            return False
        
        self.status = 'sending'
        self.started_at = timezone.now()
        self.save()
        
        recipients = self.get_recipients()
        self.total_recipients = len(recipients)
        self.save()
        
        sent_count = 0
        failed_count = 0
        
        for recipient in recipients:
            try:
                # Create individual notification
                notification = Notification.objects.create(
                    notification_type=self.notification_type,
                    recipient=recipient,
                    sender=self.sender,
                    title=self.title,
                    message=self.message,
                    short_message=self.short_message,
                    priority=self.priority,
                    action_url=self.action_url,
                    action_text=self.action_text,
                )
                
                # Send email if needed
                if notification.send_email():
                    sent_count += 1
                else:
                    sent_count += 1  # Still count as sent even if email wasn't sent
                    
            except Exception as e:
                failed_count += 1
        
        self.sent_count = sent_count
        self.failed_count = failed_count
        self.status = 'completed' if failed_count == 0 else 'failed'
        self.completed_at = timezone.now()
        self.save()
        
        return True


class NotificationTemplate(models.Model):
    """
    Reusable notification templates
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)
    
    # Template content
    title_template = models.CharField(max_length=255)
    message_template = TinyMCEField()
    short_message_template = models.CharField(max_length=500)
    
    # Default settings
    default_priority = models.CharField(
        max_length=10, 
        choices=Notification.PRIORITY_CHOICES, 
        default='normal'
    )
    default_action_url = models.URLField(blank=True)
    default_action_text = models.CharField(max_length=100, blank=True)
    
    # Available variables for template
    available_variables = models.JSONField(
        default=list,
        help_text="List of available variables for this template"
    )
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_notification_templates'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def render(self, context):
        """Render template with given context"""
        from django.template import Template, Context
        
        title = Template(self.title_template).render(Context(context))
        message = Template(self.message_template).render(Context(context))
        short_message = Template(self.short_message_template).render(Context(context))
        
        return {
            'title': title,
            'message': message,
            'short_message': short_message,
        }


class NotificationLog(models.Model):
    """
    Log of notification activities for auditing
    """
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('read', 'Read'),
        ('email_sent', 'Email Sent'),
        ('email_failed', 'Email Failed'),
        ('deleted', 'Deleted'),
        ('bulk_sent', 'Bulk Sent'),
    ]
    
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='logs'
    )
    bulk_notification = models.ForeignKey(
        BulkNotification,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='logs'
    )
    
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_logs'
    )
    
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['notification', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        if self.notification:
            return f"{self.action} - {self.notification.title}"
        elif self.bulk_notification:
            return f"{self.action} - {self.bulk_notification.title}"
        return f"{self.action} - {self.user.username}"



