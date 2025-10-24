"""
Teams Integration Models

Models for tracking Teams integration sync operations, meeting data,
and Entra ID synchronization logs.
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class TeamsSyncLog(models.Model):
    """Model for tracking Teams integration sync operations"""
    
    SYNC_TYPES = [
        ('entra_groups', 'Entra ID Groups Sync'),
        ('entra_users', 'Entra ID Users Sync'),
        ('meeting_attendance', 'Meeting Attendance Sync'),
        ('meeting_recordings', 'Meeting Recordings Sync'),
        ('meeting_chat', 'Meeting Chat Sync'),
        ('meeting_files', 'Meeting Files Sync'),
        ('full_sync', 'Full Teams Sync'),
    ]
    
    STATUS_CHOICES = [
        ('started', 'Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partial Success'),
    ]
    
    # Integration reference
    integration = models.ForeignKey(
        'account_settings.TeamsIntegration',
        on_delete=models.CASCADE,
        related_name='sync_logs'
    )
    
    # Sync details
    sync_type = models.CharField(max_length=20, choices=SYNC_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='started')
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    
    # Sync statistics
    items_processed = models.PositiveIntegerField(default=0)
    items_created = models.PositiveIntegerField(default=0)
    items_updated = models.PositiveIntegerField(default=0)
    items_failed = models.PositiveIntegerField(default=0)
    
    # Error handling
    error_message = models.TextField(blank=True, null=True)
    error_details = models.JSONField(default=dict, blank=True)
    
    # Sync configuration
    sync_direction = models.CharField(
        max_length=20,
        choices=[
            ('to_teams', 'To Teams'),
            ('from_teams', 'From Teams'),
            ('bidirectional', 'Bidirectional')
        ],
        default='from_teams'
    )
    
    # Additional metadata
    sync_metadata = models.JSONField(default=dict, blank=True)
    api_response = models.JSONField(default=dict, blank=True)
    
    # User tracking
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teams_sync_logs'
    )
    
    class Meta:
        app_label = 'teams_integration'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['integration', 'sync_type']),
            models.Index(fields=['status', 'started_at']),
            models.Index(fields=['started_at']),
        ]
    
    def __str__(self):
        return f"{self.get_sync_type_display()} - {self.status} ({self.started_at})"
    
    def save(self, *args, **kwargs):
        # Calculate duration if completed
        if self.completed_at and self.status in ['completed', 'failed', 'partial']:
            duration = self.completed_at - self.started_at
            self.duration_seconds = int(duration.total_seconds())
        
        super().save(*args, **kwargs)
    
    def mark_completed(self, success=True, error_message=None):
        """Mark sync as completed"""
        self.completed_at = timezone.now()
        if success:
            self.status = 'completed'
        else:
            self.status = 'failed'
            if error_message:
                self.error_message = error_message
        self.save()


class TeamsMeetingSync(models.Model):
    """Model for tracking Teams meeting data synchronization"""
    
    # Conference reference
    conference = models.ForeignKey(
        'conferences.Conference',
        on_delete=models.CASCADE,
        related_name='teams_syncs'
    )
    
    # Teams meeting details
    teams_meeting_id = models.CharField(max_length=255, unique=True)
    teams_meeting_url = models.URLField(max_length=500, blank=True, null=True)
    
    # Sync status
    attendance_synced = models.BooleanField(default=False)
    recordings_synced = models.BooleanField(default=False)
    chat_synced = models.BooleanField(default=False)
    files_synced = models.BooleanField(default=False)
    
    # Sync timestamps
    last_attendance_sync = models.DateTimeField(null=True, blank=True)
    last_recording_sync = models.DateTimeField(null=True, blank=True)
    last_chat_sync = models.DateTimeField(null=True, blank=True)
    last_file_sync = models.DateTimeField(null=True, blank=True)
    
    # Meeting metadata
    meeting_duration_minutes = models.PositiveIntegerField(default=0)
    total_participants = models.PositiveIntegerField(default=0)
    meeting_status = models.CharField(
        max_length=20,
        choices=[
            ('scheduled', 'Scheduled'),
            ('in_progress', 'In Progress'),
            ('ended', 'Ended'),
            ('cancelled', 'Cancelled')
        ],
        default='scheduled'
    )
    
    # Error tracking
    sync_errors = models.JSONField(default=dict, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'teams_integration'
        indexes = [
            models.Index(fields=['conference']),
            models.Index(fields=['teams_meeting_id']),
            models.Index(fields=['meeting_status']),
        ]
    
    def __str__(self):
        return f"Teams Sync - {self.conference.title} ({self.teams_meeting_id})"
    
    def is_fully_synced(self):
        """Check if all meeting data has been synced"""
        return all([
            self.attendance_synced,
            self.recordings_synced,
            self.chat_synced,
            self.files_synced
        ])


class EntraGroupMapping(models.Model):
    """Model for mapping Entra ID groups to LMS groups"""
    
    # Integration reference
    integration = models.ForeignKey(
        'account_settings.TeamsIntegration',
        on_delete=models.CASCADE,
        related_name='entra_mappings'
    )
    
    # Entra ID group details
    entra_group_id = models.CharField(max_length=255)
    entra_group_name = models.CharField(max_length=255)
    entra_group_email = models.EmailField(blank=True, null=True)
    
    # LMS group mapping
    lms_group = models.ForeignKey(
        'groups.BranchGroup',
        on_delete=models.CASCADE,
        related_name='entra_mappings'
    )
    
    # Group type mapping
    target_group_type = models.CharField(
        max_length=10,
        choices=[
            ('user', 'User Group'),
            ('course', 'Course Group'),
        ],
        default='user',
        help_text='Type of LMS group this Entra ID group should map to'
    )
    
    # Course-specific mapping (if target_group_type is 'course')
    target_course = models.ForeignKey(
        'courses.Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entra_group_mappings',
        help_text='Specific course to map to (if course group type)'
    )
    
    # Sync configuration
    is_active = models.BooleanField(default=True)
    auto_sync_enabled = models.BooleanField(default=True)
    sync_frequency_minutes = models.PositiveIntegerField(default=60)
    
    # Sync tracking
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(
        max_length=20,
        choices=[
            ('never', 'Never Synced'),
            ('success', 'Success'),
            ('failed', 'Failed'),
            ('partial', 'Partial Success')
        ],
        default='never'
    )
    
    # Statistics
    total_users_synced = models.PositiveIntegerField(default=0)
    last_sync_users_count = models.PositiveIntegerField(default=0)
    
    # Error tracking
    sync_error = models.TextField(blank=True, null=True)
    retry_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'teams_integration'
        unique_together = ['integration', 'entra_group_id']
        indexes = [
            models.Index(fields=['integration', 'is_active']),
            models.Index(fields=['lms_group']),
            models.Index(fields=['last_sync_at']),
        ]
    
    def clean(self):
        """Validate the mapping configuration"""
        from django.core.exceptions import ValidationError
        
        # If target_group_type is 'course', target_course must be specified
        if self.target_group_type == 'course' and not self.target_course:
            raise ValidationError("Target course must be specified when mapping to course group type.")
        
        # If target_group_type is 'user', target_course should be None
        if self.target_group_type == 'user' and self.target_course:
            raise ValidationError("Target course should not be specified when mapping to user group type.")
        
        # Ensure LMS group type matches target group type
        if self.lms_group and self.lms_group.group_type != self.target_group_type:
            raise ValidationError(f"LMS group type '{self.lms_group.group_type}' does not match target group type '{self.target_group_type}'.")
    
    def create_or_update_lms_group(self):
        """Create or update the LMS group based on the mapping"""
        from groups.models import BranchGroup, CourseGroupAccess
        from courses.models import Course
        
        if not self.lms_group:
            # Create new LMS group
            self.lms_group = BranchGroup.objects.create(
                name=f"{self.entra_group_name} (Entra ID)",
                description=f"Auto-created from Entra ID group: {self.entra_group_name}",
                branch=self.integration.branch,
                group_type=self.target_group_type,
                created_by=self.integration.user
            )
            self.save()
        
        # If it's a course group, ensure course access is set up
        if self.target_group_type == 'course' and self.target_course:
            CourseGroupAccess.objects.get_or_create(
                group=self.lms_group,
                course=self.target_course,
                defaults={
                    'can_access': True,
                    'can_create_topics': True,
                    'can_manage_members': False
                }
            )
    
    def get_sync_description(self):
        """Get a human-readable description of what this mapping syncs"""
        if self.target_group_type == 'user':
            return f"Syncs Entra ID group '{self.entra_group_name}' to LMS user group '{self.lms_group.name}'"
        elif self.target_group_type == 'course' and self.target_course:
            return f"Syncs Entra ID group '{self.entra_group_name}' to LMS course group '{self.lms_group.name}' for course '{self.target_course.title}'"
        else:
            return f"Syncs Entra ID group '{self.entra_group_name}' to LMS group '{self.lms_group.name}'"
    
    def __str__(self):
        return f"{self.entra_group_name} -> {self.lms_group.name} ({self.get_target_group_type_display()})"


class TeamsUserSync(models.Model):
    """Model for tracking individual user sync operations"""
    
    # User reference
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='teams_syncs'
    )
    
    # Entra ID details
    entra_user_id = models.CharField(max_length=255, blank=True, null=True)
    entra_email = models.EmailField(blank=True, null=True)
    entra_display_name = models.CharField(max_length=255, blank=True, null=True)
    
    # Sync status
    sync_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('synced', 'Synced'),
            ('failed', 'Failed'),
            ('conflict', 'Conflict')
        ],
        default='pending'
    )
    
    # Sync details
    last_sync_at = models.DateTimeField(null=True, blank=True)
    sync_error = models.TextField(blank=True, null=True)
    sync_metadata = models.JSONField(default=dict, blank=True)
    
    # Group memberships
    entra_groups = models.JSONField(default=list, blank=True)
    lms_groups = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'teams_integration'
        unique_together = ['user', 'entra_user_id']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['entra_user_id']),
            models.Index(fields=['sync_status']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.sync_status}"
