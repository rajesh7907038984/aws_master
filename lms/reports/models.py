from django.db import models
from django.conf import settings
from django.utils import timezone
from core.utils.fields import TinyMCEField

class Report(models.Model):
    """Model for storing reports"""
    title = models.CharField(max_length=255)
    description = TinyMCEField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_reports'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    report_type = models.CharField(
        max_length=50,
        choices=[
            ('ACADEMIC', 'Academic Report'),
            ('ATTENDANCE', 'Attendance Report'),
            ('PERFORMANCE', 'Performance Report'),
            ('CUSTOM', 'Custom Report'),
            ('specific_users', 'Specific Users'),
            ('learning_progress', 'Learning Progress')
        ]
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('DRAFT', 'Draft'),
            ('PUBLISHED', 'Published'),
            ('ARCHIVED', 'Archived')
        ],
        default='DRAFT'
    )
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='shared_reports',
        blank=True
    )
    
    # Custom report configuration
    rules = models.JSONField(default=dict, blank=True, help_text="Report filtering rules")
    output_fields = models.JSONField(default=list, blank=True, help_text="Fields to include in report output")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['report_type']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return self.title

class ReportAttachment(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='report_attachments/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']
        indexes = [
            models.Index(fields=['uploaded_at']),
            models.Index(fields=['file_type']),
        ]

    def __str__(self):
        return f"{self.filename} ({self.report.title})"

class Event(models.Model):
    """Model for tracking user events in the system"""
    EVENT_TYPES = [
        ('LOGIN', 'User Login'),
        ('COURSE_START', 'Course Started'),
        ('COURSE_COMPLETE', 'Course Completed'),
        ('ASSIGNMENT_SUBMIT', 'Assignment Submitted'),
        ('QUIZ_TAKE', 'Quiz Taken'),
        ('FORUM_POST', 'Forum Post'),
        ('RESOURCE_VIEW', 'Resource Viewed'),
        ('CUSTOM', 'Custom Event'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, null=True, blank=True)
    type = models.CharField(max_length=50, choices=EVENT_TYPES)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['type']),
            models.Index(fields=['user']),
            models.Index(fields=['course']),
        ]

    def __str__(self):
        return f"{self.get_type_display()} by {self.user.username}"

class ReportTemplate(models.Model):
    """Model for storing report templates"""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    content = models.TextField(help_text="Template content with placeholders")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_report_templates'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name
