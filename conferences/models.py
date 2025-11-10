from django.db import models
from django.conf import settings
from courses.models import Course
from django.utils import timezone
import logging
logger = logging.getLogger(__name__)
from django.db.models.signals import post_delete
from django.dispatch import receiver
from account_settings.zoom import get_zoom_client
from account_settings.models import ZoomIntegration


class Conference(models.Model):
    """Model for storing conference information"""
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField(blank=True, null=True)
    timezone = models.CharField(
        max_length=100,
        default='UTC',
        help_text="Timezone for the conference"
    )
    meeting_link = models.URLField(max_length=500, blank=True, null=True)
    meeting_platform = models.CharField(
        max_length=100, 
        choices=[
            ('zoom', 'Zoom'),
            ('teams', 'Microsoft Teams'),
            ('google_meet', 'Google Meet'),
            ('webex', 'Webex'),
            ('other', 'Other Platform'),
        ],
        default="teams"
    )
    
    # Extended fields for full integration
    meeting_id = models.CharField(max_length=255, blank=True, null=True, help_text="Platform-specific meeting ID")
    meeting_password = models.CharField(max_length=100, blank=True, null=True)
    host_url = models.URLField(max_length=500, blank=True, null=True, help_text="Host start URL")
    
    # Meeting status tracking
    meeting_status = models.CharField(
        max_length=20,
        choices=[
            ('scheduled', 'Scheduled'),
            ('started', 'Started'),
            ('ended', 'Ended'),
            ('cancelled', 'Cancelled')
        ],
        default='scheduled'
    )
    
    # Sync status for post-meeting data
    data_sync_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('failed', 'Failed')
        ],
        default='pending'
    )
    last_sync_at = models.DateTimeField(blank=True, null=True)
    
    # Auto recording status tracking
    auto_recording_status = models.CharField(
        max_length=30,
        choices=[
            ('pending', 'Pending Setup'),
            ('enabled', 'Recording Enabled'),
            ('failed_no_integration', 'Failed - No Integration'),
            ('failed_invalid_credentials', 'Failed - Invalid Credentials'),
            ('failed_auth', 'Failed - Authentication Error'),
            ('failed_api_error', 'Failed - API Error'),
            ('failed_exception', 'Failed - System Error'),
            ('not_applicable', 'Not Applicable')
        ],
        default='pending',
        help_text="Status of automatic cloud recording setup"
    )
    auto_recording_enabled_at = models.DateTimeField(blank=True, null=True, help_text="When auto recording was successfully enabled")
    
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='conferences',
        null=True,
        blank=True
    )
    rubric = models.ForeignKey(
        'lms_rubrics.Rubric',
        on_delete=models.SET_NULL,
        related_name='conferences',
        null=True,
        blank=True,
        help_text="Optional rubric for this conference"
    )
    visibility = models.CharField(
        max_length=20,
        choices=[
            ('public', 'Public'),
            ('private', 'Private')
        ],
        default='public'
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Draft'),
            ('published', 'Published')
        ],
        default='draft'
    )
    
    # Access control
    default_join_type = models.CharField(
        max_length=20,
        choices=[
            ('guest', 'Guest Join (No Registration Required)'),
            ('authenticated', 'Authenticated Users Only'),
            ('registered', 'Course Registered Users Only')
        ],
        default='guest',
        help_text="Default behavior when users access this conference directly"
    )
    
    # Join experience type
    join_experience = models.CharField(
        max_length=20,
        choices=[
            ('direct', 'Direct Join (Name only, immediate join)'),
            ('standard', 'Standard Guest Form (Name + Email)'),
        ],
        default='direct',
        help_text="Type of guest join experience"
    )
    
    # Join method restrictions
    allowed_join_methods = models.CharField(
        max_length=30,
        choices=[
            ('auto_registered_only', 'Auto-Registered Join Only'),
            ('manual_registration', 'Manual Registration Only'),
        ],
        default='auto_registered_only',
        help_text="Which join methods are allowed for this conference"
    )
    
    # Multiple time slots feature
    use_time_slots = models.BooleanField(
        default=False,
        help_text="Enable multiple time slot options for learners to choose from"
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conferences'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'conferences'
        ordering = ['-date', '-start_time']
        indexes = [
            models.Index(fields=['date', 'start_time']),
            models.Index(fields=['created_by']),
            models.Index(fields=['course']),
            models.Index(fields=['status']),
            models.Index(fields=['meeting_status']),
            models.Index(fields=['data_sync_status']),
            models.Index(fields=['auto_recording_status']),
            models.Index(fields=['use_time_slots']),
        ]

    def get_course_info(self):
        """
        Get course information for this conference.
        Returns course title and whether it's from direct relationship or topic-based.
        """
        # Check direct course relationship first
        if self.course:
            return {
                'title': self.course.title,
                'course': self.course,
                'source': 'direct'
            }
        
        # Check topic-based courses (conference -> topic -> course)
        from courses.models import CourseTopic
        topic_courses = CourseTopic.objects.filter(
            topic__conference=self
        ).select_related('course').distinct()
        
        if topic_courses.exists():
            # Return the first course found through topics
            course_topic = topic_courses.first()
            return {
                'title': course_topic.course.title,
                'course': course_topic.course,
                'source': 'topic'
            }
        
        # No course found
        return None

    def is_available_for_user(self, user):
        """Check if conference is available for the user to access"""
        if self.status != 'published':
            return False
        
        # For non-learner roles, allow access based on role permissions
        if user.role in ['instructor', 'admin', 'superadmin'] or user.is_superuser:
            return True
        
        # For learner role, apply filtering based on course enrollment and branch
        if user.role == 'learner':
            from courses.models import Course, CourseEnrollment
            
            # Get all courses that the user is enrolled in as a learner
            enrolled_course_ids = CourseEnrollment.objects.filter(user=user, user__role='learner').values_list('course_id', flat=True)
            
            # Check if conference is linked to any enrolled courses through any relationship
            linked_to_enrolled_course = (
                # Direct course relationship
                (self.course and self.course.id in enrolled_course_ids) or
                # Topic-based course relationship (if topics exist)
                Course.objects.filter(
                    id__in=enrolled_course_ids,
                    coursetopic__topic__conference=self
                ).exists()
            )
            
            # Also allow access if conference is from the same branch as the user
            # This handles cases where conferences are created for branch-wide access
            same_branch_access = (
                user.branch and 
                self.created_by.branch == user.branch
            )
            
            return linked_to_enrolled_course or same_branch_access
        
        return False

    def __str__(self):
        return self.title

    def get_simple_join_url(self):
        """
        Get a simple direct join URL for the conference
        """
        if not self.meeting_link:
            return None
            
        # For Zoom URLs, create simple direct join format
        if 'zoom.us' in self.meeting_link:
            from conferences.views import extract_meeting_id_from_any_zoom_url
            meeting_id = extract_meeting_id_from_any_zoom_url(self.meeting_link)
            
            if meeting_id:
                clean_url = f"https://zoom.us/j/{meeting_id}"
                if self.meeting_password:
                    clean_url += f"?pwd={self.meeting_password}"
                return clean_url
        
        # For non-Zoom platforms, return original URL
        return self.meeting_link


class ConferenceTimeSlot(models.Model):
    """Model for storing multiple time slot options for conferences"""
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='time_slots'
    )
    
    # Time slot details
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    timezone = models.CharField(
        max_length=100,
        default='UTC',
        help_text="Timezone for this time slot"
    )
    
    # Capacity management
    max_participants = models.IntegerField(
        default=0,
        help_text="Maximum participants for this slot (0 = unlimited)"
    )
    current_participants = models.IntegerField(
        default=0,
        help_text="Current number of participants"
    )
    
    # Meeting details (can be different for each slot)
    meeting_link = models.URLField(max_length=500, blank=True, null=True)
    meeting_id = models.CharField(max_length=255, blank=True, null=True)
    meeting_password = models.CharField(max_length=100, blank=True, null=True)
    
    # Status
    is_available = models.BooleanField(
        default=True,
        help_text="Is this slot available for selection?"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'conferences'
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['conference', 'date', 'start_time']),
            models.Index(fields=['is_available']),
        ]
    
    def __str__(self):
        return f"{self.conference.title} - {self.date} {self.start_time}"
    
    def is_full(self):
        """Check if this time slot is full"""
        if self.max_participants == 0:
            return False
        return self.current_participants >= self.max_participants
    
    def get_available_spots(self):
        """Get number of available spots"""
        if self.max_participants == 0:
            return None  # Unlimited
        return max(0, self.max_participants - self.current_participants)


class ConferenceTimeSlotSelection(models.Model):
    """Model for tracking learner's time slot selection"""
    time_slot = models.ForeignKey(
        ConferenceTimeSlot,
        on_delete=models.CASCADE,
        related_name='selections'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='time_slot_selections'
    )
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='time_slot_selections'
    )
    
    # Outlook calendar integration
    outlook_event_id = models.CharField(max_length=255, blank=True, null=True)
    calendar_added = models.BooleanField(default=False)
    calendar_add_attempted_at = models.DateTimeField(blank=True, null=True)
    calendar_error = models.TextField(blank=True, null=True)
    
    # Selection metadata
    selected_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    class Meta:
        app_label = 'conferences'
        unique_together = ['conference', 'user']
        indexes = [
            models.Index(fields=['time_slot', 'user']),
            models.Index(fields=['conference', 'user']),
            models.Index(fields=['selected_at']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.time_slot}"


class ConferenceAttendance(models.Model):
    """Model for tracking conference attendance"""
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conference_attendances'
    )
    
    # Attendance tracking fields
    participant_id = models.CharField(max_length=255, blank=True, null=True, help_text="Platform-specific participant ID")
    join_time = models.DateTimeField(blank=True, null=True)
    leave_time = models.DateTimeField(blank=True, null=True)
    duration_minutes = models.IntegerField(default=0, help_text="Attendance duration in minutes")
    
    # Status tracking
    attendance_status = models.CharField(
        max_length=20,
        choices=[
            ('present', 'Present'),
            ('absent', 'Absent'),
            ('late', 'Late'),
            ('left_early', 'Left Early')
        ],
        default='absent'
    )
    
    # Additional tracking info
    device_info = models.JSONField(default=dict, blank=True, help_text="Device/browser information")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'conferences'
        unique_together = ['conference', 'user']
        indexes = [
            models.Index(fields=['conference', 'user']),
            models.Index(fields=['attendance_status']),
            models.Index(fields=['join_time']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.conference.title} ({self.attendance_status})"


class ConferenceRecording(models.Model):
    """Model for storing conference recordings"""
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='recordings'
    )
    
    # Recording details
    recording_id = models.CharField(max_length=255, unique=True, help_text="Platform-specific recording ID")
    title = models.CharField(max_length=255)
    recording_type = models.CharField(
        max_length=50,
        choices=[
            ('cloud', 'Cloud Recording'),
            ('local', 'Local Recording'),
            ('audio_only', 'Audio Only'),
            ('shared_screen', 'Shared Screen')
        ],
        default='cloud'
    )
    
    # File information
    file_url = models.URLField(max_length=500, blank=True, null=True, help_text="Direct download/stream URL")
    file_size = models.BigIntegerField(default=0, help_text="File size in bytes")
    duration_minutes = models.IntegerField(default=0, help_text="Recording duration in minutes")
    file_format = models.CharField(max_length=10, default='mp4')
    
    # Storage and access
    download_url = models.URLField(max_length=500, blank=True, null=True, help_text="Download URL with auth")
    password_protected = models.BooleanField(default=False)
    recording_password = models.CharField(max_length=100, blank=True, null=True)
    
    # Status and availability
    status = models.CharField(
        max_length=20,
        choices=[
            ('processing', 'Processing'),
            ('available', 'Available'),
            ('expired', 'Expired'),
            ('deleted', 'Deleted')
        ],
        default='processing'
    )
    expires_at = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'conferences'
        indexes = [
            models.Index(fields=['conference']),
            models.Index(fields=['recording_id']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.title} - {self.conference.title}"


class ConferenceFile(models.Model):
    """Model for files shared during conferences"""
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='shared_files'
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shared_conference_files'
    )
    
    # File details
    filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file_url = models.URLField(max_length=500, blank=True, null=True, help_text="Platform download URL")
    file_size = models.BigIntegerField(default=0, help_text="File size in bytes")
    file_type = models.CharField(max_length=50)
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    
    # Local storage (optional)
    local_file = models.FileField(upload_to='conference_files/%Y/%m/%d/', blank=True, null=True)
    
    # Metadata
    shared_at = models.DateTimeField()
    downloaded_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'conferences'
        indexes = [
            models.Index(fields=['conference']),
            models.Index(fields=['shared_by']),
            models.Index(fields=['shared_at']),
            models.Index(fields=['file_type']),
        ]

    def __str__(self):
        return f"{self.filename} - {self.conference.title}"


class ConferenceChat(models.Model):
    """Model for storing chat messages from conferences"""
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='chat_messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conference_chat_messages',
        null=True,
        blank=True  # Some platforms may not provide user mapping
    )
    
    # Message details
    sender_name = models.CharField(max_length=255, help_text="Display name from platform")
    message_text = models.TextField()
    message_type = models.CharField(
        max_length=20,
        choices=[
            ('text', 'Text Message'),
            ('file', 'File Share'),
            ('system', 'System Message'),
            ('poll', 'Poll'),
            ('reaction', 'Reaction')
        ],
        default='text'
    )
    
    # Timestamp and metadata
    sent_at = models.DateTimeField()
    platform_message_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Additional data (polls, reactions, etc.)
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'conferences'
        indexes = [
            models.Index(fields=['conference']),
            models.Index(fields=['sender']),
            models.Index(fields=['sent_at']),
            models.Index(fields=['message_type']),
        ]
        ordering = ['sent_at']

    def __str__(self):
        return f"{self.sender_name}: {self.message_text[:50]}..."


class ConferenceSyncLog(models.Model):
    """Model for tracking data synchronization from conferencing platforms"""
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='sync_logs'
    )
    
    sync_type = models.CharField(
        max_length=20,
        choices=[
            ('attendance', 'Attendance Data'),
            ('recordings', 'Recordings'),
            ('files', 'Shared Files'),
            ('chat', 'Chat Messages'),
            ('full', 'Full Sync')
        ]
    )
    
    status = models.CharField(
        max_length=20,
        choices=[
            ('started', 'Started'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('partial', 'Partial Success')
        ]
    )
    
    # Sync details
    items_processed = models.IntegerField(default=0)
    items_failed = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    sync_duration_seconds = models.IntegerField(default=0)
    
    # Platform response data
    platform_response = models.JSONField(default=dict, blank=True)
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        app_label = 'conferences'
        indexes = [
            models.Index(fields=['conference']),
            models.Index(fields=['sync_type']),
            models.Index(fields=['status']),
            models.Index(fields=['started_at']),
        ]
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.conference.title} - {self.sync_type} ({self.status})"


class GuestParticipant(models.Model):
    """Model for tracking guest participants who join conferences without user accounts"""
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='guest_participants'
    )
    
    # Guest identification
    participation_id = models.CharField(max_length=255, unique=True, help_text="Unique ID for tracking guest participation")
    guest_name = models.CharField(max_length=255, blank=True, null=True, help_text="Optional name provided by guest")
    guest_email = models.EmailField(blank=True, null=True, help_text="Optional email provided by guest")
    
    # Participation tracking
    join_time = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    session_duration_minutes = models.IntegerField(default=0)
    
    # Device and session information
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    device_info = models.JSONField(default=dict, blank=True)
    
    # Participation status
    participation_status = models.CharField(
        max_length=20,
        choices=[
            ('joined', 'Joined Conference'),
            ('active', 'Active in Meeting'),
            ('left', 'Left Conference'),
            ('disconnected', 'Disconnected')
        ],
        default='joined'
    )
    
    # Meeting platform specific data
    platform_participant_id = models.CharField(max_length=255, blank=True, null=True, help_text="Platform-specific participant ID when available")
    platform_metadata = models.JSONField(default=dict, blank=True, help_text="Additional platform-specific data")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'conferences'
        indexes = [
            models.Index(fields=['conference', 'participation_id']),
            models.Index(fields=['participation_id']),
            models.Index(fields=['join_time']),
            models.Index(fields=['participation_status']),
        ]
        ordering = ['-join_time']

    def __str__(self):
        name = self.guest_name or f"Guest-{self.participation_id[:8]}"
        return f"{name} - {self.conference.title}"

    def get_display_name(self):
        """Get a display name for the guest participant"""
        if self.guest_name:
            return self.guest_name
        if self.guest_email:
            return self.guest_email.split('@')[0]
        return f"Guest-{self.participation_id[:8]}"


class BranchZoomAccess(models.Model):
    """Model for managing branch-level access to Zoom integrations"""
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='zoom_access_permissions'
    )
    zoom_integration = models.ForeignKey(
        'account_settings.ZoomIntegration',
        on_delete=models.CASCADE,
        related_name='branch_permissions'
    )
    # Granular permissions
    can_create_meetings = models.BooleanField(default=True)
    can_view_recordings = models.BooleanField(default=True)
    can_view_attendance = models.BooleanField(default=True)
    can_view_chat_logs = models.BooleanField(default=True)
    can_download_files = models.BooleanField(default=True)
    
    # Permission levels
    PERMISSION_LEVELS = [
        ('full', 'Full Access'),
        ('meetings_only', 'Meetings Only'),
        ('view_only', 'View Only'),
        ('restricted', 'Restricted Access')
    ]
    permission_level = models.CharField(
        max_length=20,
        choices=PERMISSION_LEVELS,
        default='full'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'conferences'
        unique_together = ['branch', 'zoom_integration']
        indexes = [
            models.Index(fields=['branch']),
            models.Index(fields=['zoom_integration']),
        ]
    
    def __str__(self):
        return f"{self.branch.name} - {self.zoom_integration.user.get_full_name()} ({self.permission_level})"


class ConferenceRubricEvaluation(models.Model):
    """Model for storing conference rubric evaluations"""
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='rubric_evaluations')
    attendance = models.ForeignKey(ConferenceAttendance, on_delete=models.CASCADE, related_name='rubric_evaluations')
    criterion = models.ForeignKey('lms_rubrics.RubricCriterion', on_delete=models.CASCADE, related_name='conference_evaluations')
    rating = models.ForeignKey('lms_rubrics.RubricRating', on_delete=models.SET_NULL, null=True, blank=True, related_name='conference_evaluations')
    points = models.FloatField(default=0)
    comments = models.TextField(blank=True)
    evaluated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='conference_rubric_evaluations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'conferences'
        unique_together = ['attendance', 'criterion']
        ordering = ['criterion__position']
    
    def __str__(self):
        return f"Evaluation for {self.attendance.user.get_full_name()} - {self.conference.title} - {self.criterion}"
        
    def clean(self):
        """Validate evaluation data"""
        from django.core.exceptions import ValidationError
        if self.points < 0:
            raise ValidationError({'points': 'Points cannot be negative'})
        if self.points > self.criterion.points:
            raise ValidationError({'points': f'Points cannot exceed criterion maximum of {self.criterion.points}'})
        super().clean()
        
    def save(self, *args, **kwargs):
        # Ensure points don't exceed criterion maximum
        if self.points > self.criterion.points:
            self.points = self.criterion.points
        super().save(*args, **kwargs)


class ConferenceParticipant(models.Model):
    """
    Streamlined participant tracking model - created when user clicks join.
    No pre-registration required - tracks participation from click to completion.
    """
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name='participants'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conference_participations',
        null=True,
        blank=True  # Allow guest participants without user accounts
    )
    
    # Unique tracking identifiers
    participant_id = models.CharField(max_length=255, unique=True, help_text="Unique ID generated on join click")
    session_token = models.CharField(max_length=255, unique=True, help_text="Unique session token for this participation")
    
    # Participant info (for guests or user override)
    display_name = models.CharField(max_length=255, help_text="Name shown in meeting")
    email_address = models.EmailField(blank=True, null=True, help_text="Email used in meeting")
    
    # Join method tracking
    JOIN_METHODS = [
        ('auto_registered', 'Auto-Registered Join'),
        ('manual_registration', 'Manual Registration'),
        ('guest', 'Guest Join')
    ]
    join_method = models.CharField(
        max_length=30,
        choices=JOIN_METHODS,
        default='auto_registered',
        help_text="How the user joined the conference"
    )
    
    # Participation status tracking
    PARTICIPATION_STATUS = [
        ('clicked_join', 'Clicked Join Button'),
        ('redirected_to_platform', 'Redirected to Meeting Platform'),
        ('joined_meeting', 'Joined Meeting'),
        ('active_in_meeting', 'Active in Meeting'),
        ('left_meeting', 'Left Meeting'),
        ('meeting_ended', 'Meeting Ended'),
        ('sync_completed', 'Data Sync Completed')
    ]
    participation_status = models.CharField(
        max_length=30,
        choices=PARTICIPATION_STATUS,
        default='clicked_join'
    )
    
    # Timing data
    click_timestamp = models.DateTimeField(auto_now_add=True, help_text="When user clicked join")
    join_timestamp = models.DateTimeField(blank=True, null=True, help_text="When user actually joined meeting")
    leave_timestamp = models.DateTimeField(blank=True, null=True, help_text="When user left meeting")
    last_activity = models.DateTimeField(auto_now=True, help_text="Last activity update")
    
    # Platform-specific data
    platform_participant_id = models.CharField(max_length=255, blank=True, null=True, help_text="Platform's participant ID")
    platform_user_id = models.CharField(max_length=255, blank=True, null=True, help_text="Platform's user ID")
    platform_session_id = models.CharField(max_length=255, blank=True, null=True, help_text="Platform's session ID")
    
    # Device and session information
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    device_fingerprint = models.CharField(max_length=255, blank=True, null=True)
    
    # Comprehensive tracking data
    tracking_data = models.JSONField(default=dict, blank=True, help_text="All tracking information")
    
    # Attendance summary
    total_duration_minutes = models.IntegerField(default=0, help_text="Total participation duration")
    attendance_percentage = models.FloatField(default=0.0, help_text="Percentage of meeting attended")
    
    # Data sync status
    DATA_SYNC_STATUS = [
        ('pending', 'Sync Pending'),
        ('in_progress', 'Sync In Progress'),
        ('completed', 'Sync Completed'),
        ('partial', 'Partial Data'),
        ('failed', 'Sync Failed')
    ]
    sync_status = models.CharField(
        max_length=20,
        choices=DATA_SYNC_STATUS,
        default='pending'
    )
    last_sync_at = models.DateTimeField(blank=True, null=True)
    sync_errors = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'conferences'
        unique_together = ['conference', 'user', 'participant_id']
        indexes = [
            models.Index(fields=['conference', 'user']),
            models.Index(fields=['participant_id']),
            models.Index(fields=['session_token']),
            models.Index(fields=['participation_status']),
            models.Index(fields=['click_timestamp']),
            models.Index(fields=['platform_participant_id']),
            models.Index(fields=['sync_status']),
        ]
        ordering = ['-click_timestamp']

    def __str__(self):
        if self.user:
            return f"{self.display_name} ({self.user.username}) - {self.conference.title}"
        return f"{self.display_name} (Guest) - {self.conference.title}"

    def generate_tracking_url(self, base_meeting_url):
        """
        Generate meeting URL with participant tracking parameters.
        CRITICAL: Always ensure direct join URLs for learners, never registration URLs.
        """
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Special handling for Zoom URLs - ALWAYS ensure direct join format
        if 'zoom.us' in base_meeting_url:
            # Import the conversion functions
            from conferences.views import force_convert_registration_url_to_direct_join, clean_zoom_url_format
            
            logger.info(f"🎯 Processing Zoom URL for learner join: {base_meeting_url}")
            
            # CRITICAL FIX: Always convert to direct join, regardless of current URL format
            # This ensures learners NEVER see registration forms
            try:
                # Method 1: If URL contains 'register', force convert to direct join
                if 'register' in base_meeting_url:
                    logger.info(" Converting registration URL to direct join")
                    tracking_url = force_convert_registration_url_to_direct_join(base_meeting_url)
                    conversion_method = 'force_convert_registration'
                else:
                    # Method 2: For non-registration URLs, still clean them to ensure direct join format
                    logger.info(" Cleaning URL format for direct join")
                    tracking_url = clean_zoom_url_format(self.conference) if hasattr(self, 'conference') else base_meeting_url
                    conversion_method = 'clean_zoom_format'
                
                # DOUBLE CHECK: If the converted URL still contains 'register', force another conversion
                if 'register' in tracking_url:
                    logger.warning(" URL still contains 'register' after conversion, forcing another conversion")
                    tracking_url = force_convert_registration_url_to_direct_join(tracking_url)
                    conversion_method = 'double_force_convert'
                
                # TRIPLE CHECK: If it's still a registration URL, create a manual direct join URL
                if 'register' in tracking_url:
                    logger.error(" URL conversion failed, creating manual direct join URL")
                    # Extract meeting ID and create simple direct join URL
                    from conferences.views import extract_meeting_id_from_any_zoom_url
                    meeting_id = extract_meeting_id_from_any_zoom_url(base_meeting_url)
                    if meeting_id:
                        # Extract domain from original URL
                        import re
                        domain_match = re.search(r'(https?://[^/]+)', base_meeting_url)
                        domain = domain_match.group(1) if domain_match else 'https://zoom.us'
                        
                        # Create simple direct join URL
                        tracking_url = f"{domain}/j/{meeting_id}"
                        
                        # Add password if available
                        if self.conference.meeting_password:
                            tracking_url += f"?pwd={self.conference.meeting_password}"
                        
                        conversion_method = 'manual_direct_join'
                        logger.info(f" Created manual direct join URL: {tracking_url}")
                    else:
                        logger.error(" Could not extract meeting ID, using original URL")
                        tracking_url = base_meeting_url
                        conversion_method = 'failed_fallback'
                
                # Final validation: Log the result
                if 'register' in tracking_url:
                    logger.error(f" CRITICAL: Learner will still see registration form! URL: {tracking_url}")
                else:
                    logger.info(f" SUCCESS: Learner will get direct join URL: {tracking_url}")
                
                #  NOW ADD NAME AND EMAIL TO THE CLEAN ZOOM URL
                # Parse the clean URL and add user credentials
                from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
                parsed_url = urlparse(tracking_url)
                query_params = parse_qs(parsed_url.query)
                
                # Add user name and email to URL parameters
                query_params['uname'] = [self.display_name]
                if self.email_address:
                    query_params['email'] = [self.email_address]
                
                # Add tracking parameters for LMS
                query_params['lms_participant_id'] = [self.participant_id]
                query_params['lms_session'] = [self.session_token]
                
                # Add return URL for proper redirection after meeting
                from django.urls import reverse
                from django.conf import settings
                # Use settings BASE_URL instead of hardcoded domain
                base_url = getattr(settings, 'BASE_URL', 
                                   f"https://{getattr(settings, 'PRIMARY_DOMAIN', 'localhost')}")
                return_url = f"{base_url}{reverse('conferences:conference_redirect_handler', args=[self.conference.id])}"
                query_params['return_url'] = [return_url]
                
                # Rebuild URL with all parameters
                new_query = urlencode(query_params, doseq=True)
                final_tracking_url = urlunparse((
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    new_query,
                    parsed_url.fragment
                ))
                
                logger.info(f" ENHANCED: Added user credentials to URL: {final_tracking_url}")
                
                # Update tracking data with detailed conversion info
                self.tracking_data.update({
                    'tracking_url_generated': True,
                    'tracking_url_timestamp': timezone.now().isoformat(),
                    'original_url': base_meeting_url,
                    'converted_url': tracking_url,
                    'final_url_with_credentials': final_tracking_url,
                    'conversion_method': conversion_method,
                    'tracking_method': 'zoom_direct_join_with_credentials',
                    'note': 'Converted to direct join URL with user credentials auto-filled',
                    'user_credentials': {
                        'name_added': 'uname' in final_tracking_url,
                        'email_added': 'email' in final_tracking_url,
                        'display_name': self.display_name,
                        'email_address': self.email_address
                    },
                    'url_validation': {
                        'contains_register': 'register' in final_tracking_url,
                        'is_direct_join': '/j/' in final_tracking_url or '/w/' in final_tracking_url,
                        'conversion_successful': 'register' not in final_tracking_url,
                        'has_user_name': 'uname=' in final_tracking_url,
                        'has_user_email': 'email=' in final_tracking_url
                    }
                })
                self.save(update_fields=['tracking_data'])
                
                return final_tracking_url
                
            except Exception as e:
                logger.error(f" Error in Zoom URL conversion: {str(e)}")
                # Fallback: try to create a simple direct join URL
                try:
                    from conferences.views import extract_meeting_id_from_any_zoom_url
                    meeting_id = extract_meeting_id_from_any_zoom_url(base_meeting_url)
                    if meeting_id:
                        fallback_url = f"https://zoom.us/j/{meeting_id}"
                        if self.conference.meeting_password:
                            fallback_url += f"?pwd={self.conference.meeting_password}"
                        logger.info(f" Created fallback direct join URL: {fallback_url}")
                        return fallback_url
                except Exception as fe:
                    logger.error(f" Fallback URL creation failed: {str(fe)}")
                
                # Ultimate fallback: return original URL
                return base_meeting_url
        
        # For non-Zoom platforms, use the original approach
        parsed_url = urlparse(base_meeting_url)
        query_params = parse_qs(parsed_url.query)
        
        # Add tracking parameters
        query_params['lms_participant_id'] = [self.participant_id]
        query_params['lms_session'] = [self.session_token]
        query_params['uname'] = [self.display_name]
        if self.email_address:
            query_params['email'] = [self.email_address]
        
        # Rebuild URL with tracking parameters
        new_query = urlencode(query_params, doseq=True)
        tracking_url = urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment
        ))
        
        # Update tracking data
        self.tracking_data.update({
            'tracking_url_generated': True,
            'tracking_url_timestamp': timezone.now().isoformat(),
            'original_url': base_meeting_url,
            'enhanced_url': tracking_url,
            'platform': 'non_zoom'
        })
        self.save(update_fields=['tracking_data'])
        
        return tracking_url

    def update_participation_status(self, new_status, additional_data=None):
        """Update participation status with optional additional data"""
        self.participation_status = new_status
        if additional_data:
            self.tracking_data.update(additional_data)
        self.save(update_fields=['participation_status', 'tracking_data', 'updated_at'])

    def record_platform_data(self, platform_data):
        """Record data received from meeting platform"""
        if 'participant_id' in platform_data:
            self.platform_participant_id = platform_data['participant_id']
        if 'user_id' in platform_data:
            self.platform_user_id = platform_data['user_id']
        if 'session_id' in platform_data:
            self.platform_session_id = platform_data['session_id']
        
        # Update tracking data
        self.tracking_data.update({
            'platform_data_recorded': True,
            'platform_data_timestamp': timezone.now().isoformat(),
            'platform_data': platform_data
        })
        
        self.save(update_fields=[
            'platform_participant_id', 'platform_user_id', 'platform_session_id',
            'tracking_data', 'updated_at'
        ])

    def calculate_attendance_metrics(self):
        """Calculate attendance percentage and duration"""
        if self.join_timestamp and self.leave_timestamp:
            duration = self.leave_timestamp - self.join_timestamp
            self.total_duration_minutes = int(duration.total_seconds() / 60)
            
            # Calculate percentage based on meeting duration
            if self.conference.start_time and self.conference.end_time:
                from dateutil import parser as date_parser
                
                # Ensure date and time are proper objects, not strings
                conf_date = date_parser.parse(self.conference.date).date() if isinstance(self.conference.date, str) else self.conference.date
                conf_start = date_parser.parse(self.conference.start_time).time() if isinstance(self.conference.start_time, str) else self.conference.start_time
                conf_end = date_parser.parse(self.conference.end_time).time() if isinstance(self.conference.end_time, str) else self.conference.end_time
                
                meeting_start = timezone.datetime.combine(conf_date, conf_start)
                meeting_end = timezone.datetime.combine(conf_date, conf_end)
                if hasattr(meeting_start, 'replace'):
                    meeting_start = meeting_start.replace(tzinfo=timezone.get_current_timezone())
                    meeting_end = meeting_end.replace(tzinfo=timezone.get_current_timezone())
                
                total_meeting_duration = meeting_end - meeting_start
                total_meeting_minutes = int(total_meeting_duration.total_seconds() / 60)
                
                if total_meeting_minutes > 0:
                    self.attendance_percentage = min(100.0, (self.total_duration_minutes / total_meeting_minutes) * 100)
            
            self.save(update_fields=['total_duration_minutes', 'attendance_percentage'])

    @classmethod
    def create_for_user_click(cls, conference, user, request=None):
        """Create participant record when user clicks join"""
        import uuid
        from django.utils import timezone
        
        # Generate unique identifiers
        participant_id = f"lms_{conference.id}_{user.id}_{uuid.uuid4().hex[:8]}"
        session_token = uuid.uuid4().hex
        
        # Prepare user info
        display_name = user.get_full_name() or user.username
        email_address = user.email
        
        # Gather device info
        device_info = {}
        if request:
            device_info = {
                'ip_address': request.META.get('REMOTE_ADDR'),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'http_host': request.META.get('HTTP_HOST'),
                'request_method': request.method,
                'click_timestamp': timezone.now().isoformat()
            }
        
        # Create participant record
        participant = cls.objects.create(
            conference=conference,
            user=user,
            participant_id=participant_id,
            session_token=session_token,
            display_name=display_name,
            email_address=email_address,
            ip_address=device_info.get('ip_address'),
            user_agent=device_info.get('user_agent'),
            tracking_data={
                'join_method': 'lms_click_to_track',
                'device_info': device_info,
                'user_profile': {
                    'user_id': user.id,
                    'username': user.username,
                    'full_name': display_name,
                    'email': email_address,
                    'role': user.role if hasattr(user, 'role') else 'unknown'
                }
            }
        )
        
        return participant


class ParticipantTrackingData(models.Model):
    """
    Detailed tracking data for each participant across different data types
    """
    participant = models.ForeignKey(
        ConferenceParticipant,
        on_delete=models.CASCADE,
        related_name='tracking_details'
    )
    
    DATA_TYPES = [
        ('attendance', 'Attendance Data'),
        ('recording', 'Recording Data'),
        ('chat', 'Chat Messages'),
        ('files', 'Shared Files'),
        ('polls', 'Poll Responses'),
        ('reactions', 'Reactions'),
        ('breakout', 'Breakout Room Data'),
    ]
    data_type = models.CharField(max_length=20, choices=DATA_TYPES)
    
    # Raw data from platform
    platform_data = models.JSONField(default=dict, help_text="Raw data from meeting platform")
    
    # Processed/normalized data
    processed_data = models.JSONField(default=dict, help_text="Processed and normalized data")
    
    # Timestamps
    recorded_at = models.DateTimeField(help_text="When this data was recorded in the platform")
    synced_at = models.DateTimeField(auto_now_add=True, help_text="When this data was synced to LMS")
    
    # Data quality
    data_quality_score = models.FloatField(default=1.0, help_text="Quality score (0-1) for this data")
    has_errors = models.BooleanField(default=False)
    error_details = models.TextField(blank=True, null=True)

    class Meta:
        app_label = 'conferences'
        unique_together = ['participant', 'data_type', 'recorded_at']
        indexes = [
            models.Index(fields=['participant', 'data_type']),
            models.Index(fields=['recorded_at']),
            models.Index(fields=['synced_at']),
            models.Index(fields=['data_quality_score']),
        ]
        ordering = ['-recorded_at']

    def __str__(self):
        return f"{self.participant.display_name} - {self.get_data_type_display()} ({self.recorded_at})"


@receiver(post_delete, sender=Conference)
def delete_zoom_meeting_on_conference_delete(sender, instance, **kwargs):
    """Automatically delete the Zoom meeting when a Conference instance is removed"""
    if instance.meeting_platform == 'zoom' and instance.meeting_id:
        logger.info(f"Signal triggered: Attempting to delete Zoom meeting {instance.meeting_id} for conference {instance.id}")
        try:
            # Attempt to find a matching Zoom integration for the conference creator
            integration = ZoomIntegration.objects.filter(user=instance.created_by, is_active=True).first()
            # If none on user, try branch-level integration
            if not integration and hasattr(instance.created_by, 'branch') and instance.created_by.branch:
                integration = ZoomIntegration.objects.filter(
                    user__branch=instance.created_by.branch,
                    is_active=True
                ).exclude(user=instance.created_by).first()
                logger.info(f"Using branch-level integration for user {instance.created_by.id}")
            # Fallback to any active integration
            if not integration:
                integration = ZoomIntegration.objects.filter(is_active=True).first()
                if integration:
                    logger.info(f"Using fallback integration from user {integration.user.id}")
            
            if integration:
                client = get_zoom_client(integration)
                result = client.delete_meeting(instance.meeting_id)
                if result.get('success'):
                    logger.info(f"Signal handler: Successfully deleted Zoom meeting {instance.meeting_id} for conference {instance.id}")
                else:
                    logger.error(f"Signal handler: Failed to delete Zoom meeting {instance.meeting_id} for conference {instance.id}: {result.get('error')}")
            else:
                logger.warning(
                    f"Signal handler: No active Zoom integration found to delete meeting {instance.meeting_id} for conference {instance.id}"
                )
        except Exception as e:
            logger.exception(
                f"Signal handler: Error deleting Zoom meeting {instance.meeting_id} for conference {instance.id}: {str(e)}"
            )
