from django.db import models
from django.conf import settings
from django.utils import timezone
from courses.models import Topic
import json


class ScormPackage(models.Model):
    """
    Model to store SCORM package information
    """
    SCORM_VERSION_CHOICES = [
        ('1.1', 'SCORM 1.1'),
        ('1.2', 'SCORM 1.2'),
        ('2004', 'SCORM 2004'),
        ('xapi', 'xAPI/Tin Can'),
        ('dual', 'SCORM + xAPI Dual'),
        ('legacy', 'Legacy SCORM'),
        ('html5', 'HTML5 Package'),
        ('storyline', 'Articulate Storyline'),
        ('captivate', 'Adobe Captivate'),
        ('lectora', 'Lectora'),
        ('unknown', 'Unknown Format'),
    ]
    
    topic = models.OneToOneField(
        Topic,
        on_delete=models.CASCADE,
        related_name='scorm_package'
    )
    
    # Package metadata
    version = models.CharField(max_length=10, choices=SCORM_VERSION_CHOICES, default='1.2')
    identifier = models.CharField(max_length=255, help_text="Package identifier from manifest")
    title = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    
    # Package file storage
    package_file = models.FileField(
        upload_to='scorm_packages/%Y/%m/',
        max_length=500,
        help_text="Original SCORM ZIP package"
    )
    extracted_path = models.CharField(
        max_length=500,
        help_text="Path to extracted SCORM content"
    )
    
    # Launch information
    launch_url = models.CharField(
        max_length=500,
        help_text="Relative path to launch file (index.html, story.html, etc.)"
    )
    
    # Manifest data
    manifest_data = models.JSONField(
        default=dict,
        help_text="Parsed manifest.xml data"
    )
    
    # Tracking settings
    mastery_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Mastery score from manifest"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'scorm_package'
        verbose_name = 'SCORM Package'
        verbose_name_plural = 'SCORM Packages'
    
    def __str__(self):
        return f"{self.title} ({self.version})"


class ScormAttempt(models.Model):
    """
    Model to track individual SCORM attempts by users
    """
    STATUS_CHOICES = [
        ('not_attempted', 'Not Attempted'),
        ('incomplete', 'Incomplete'),
        ('completed', 'Completed'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scorm_attempts'
    )
    scorm_package = models.ForeignKey(
        ScormPackage,
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    
    # Attempt tracking
    attempt_number = models.IntegerField(default=1)
    
    # SCORM data model
    lesson_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='not_attempted'
    )
    completion_status = models.CharField(max_length=20, default='incomplete')
    success_status = models.CharField(max_length=20, default='unknown')
    
    # Score tracking
    score_raw = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    score_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=0
    )
    score_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=100
    )
    score_scaled = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Scaled score (0-1)"
    )
    
    # Enhanced time tracking
    total_time = models.CharField(
        max_length=50,
        default='0000:00:00.00',
        help_text="Total time in SCORM format (hhhh:mm:ss.ss)"
    )
    session_time = models.CharField(
        max_length=50,
        default='0000:00:00.00',
        help_text="Session time in SCORM format"
    )
    # Additional time tracking fields
    time_spent_seconds = models.IntegerField(
        default=0,
        help_text="Total time spent in seconds for easy calculation"
    )
    session_start_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When current session started"
    )
    session_end_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When current session ended"
    )
    
    # Enhanced location and progress tracking
    lesson_location = models.CharField(
        max_length=1000,
        blank=True,
        help_text="Bookmark/location in the course"
    )
    suspend_data = models.TextField(
        blank=True,
        help_text="Suspend data for resuming"
    )
    # Additional progress tracking fields
    last_visited_slide = models.CharField(
        max_length=255,
        blank=True,
        help_text="Last visited slide/page identifier"
    )
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Progress percentage (0-100)"
    )
    completed_slides = models.IntegerField(
        default=0,
        help_text="Number of completed slides"
    )
    total_slides = models.IntegerField(
        default=0,
        help_text="Total number of slides in the course"
    )
    navigation_history = models.JSONField(
        default=list,
        help_text="History of slide navigation with timestamps"
    )
    
    # Additional SCORM data
    entry = models.CharField(
        max_length=20,
        default='ab-initio',
        help_text="Entry mode (ab-initio, resume)"
    )
    exit_mode = models.CharField(max_length=20, blank=True)
    
    # Enhanced SCORM data storage
    cmi_data = models.JSONField(
        default=dict,
        help_text="Complete CMI data model storage"
    )
    # Additional tracking data
    detailed_tracking = models.JSONField(
        default=dict,
        help_text="Detailed tracking data including slide visits, time per slide, etc."
    )
    session_data = models.JSONField(
        default=dict,
        help_text="Current session data including start time, current slide, etc."
    )
    
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'scorm_attempt'
        verbose_name = 'SCORM Attempt'
        verbose_name_plural = 'SCORM Attempts'
        unique_together = ['user', 'scorm_package', 'attempt_number']
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.scorm_package.title} - Attempt {self.attempt_number}"
    
    def get_percentage_score(self):
        """Calculate percentage score"""
        if self.score_raw is not None and self.score_max:
            return (float(self.score_raw) / float(self.score_max)) * 100
        return None
    
    def is_passed(self):
        """Check if attempt is passed based on mastery score"""
        if self.scorm_package.mastery_score and self.score_raw is not None:
            return self.score_raw >= self.scorm_package.mastery_score
        return self.lesson_status in ['passed', 'completed']


class ScormInteraction(models.Model):
    """
    Model to track detailed learner interactions (questions, activities)
    """
    INTERACTION_TYPE_CHOICES = [
        ('choice', 'Choice'),
        ('true-false', 'True/False'),
        ('fill-in', 'Fill-in'),
        ('matching', 'Matching'),
        ('performance', 'Performance'),
        ('sequencing', 'Sequencing'),
        ('likert', 'Likert'),
        ('numeric', 'Numeric'),
        ('other', 'Other'),
    ]
    
    RESULT_CHOICES = [
        ('correct', 'Correct'),
        ('incorrect', 'Incorrect'),
        ('unanticipated', 'Unanticipated'),
        ('neutral', 'Neutral'),
        ('numeric', 'Numeric'),
    ]
    
    attempt = models.ForeignKey(
        ScormAttempt,
        on_delete=models.CASCADE,
        related_name='interactions'
    )
    
    # Interaction identification
    interaction_id = models.CharField(
        max_length=255,
        help_text="Unique identifier for the interaction"
    )
    interaction_type = models.CharField(
        max_length=20,
        choices=INTERACTION_TYPE_CHOICES,
        help_text="Type of interaction"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the interaction"
    )
    
    # Response tracking
    student_response = models.TextField(
        blank=True,
        help_text="Learner's response to the interaction"
    )
    correct_response = models.TextField(
        blank=True,
        help_text="Correct response pattern"
    )
    result = models.CharField(
        max_length=20,
        choices=RESULT_CHOICES,
        blank=True,
        help_text="Result of the interaction"
    )
    
    # Scoring
    weighting = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Weight of the interaction"
    )
    score_raw = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Raw score for this interaction"
    )
    
    # Timing
    timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the interaction occurred"
    )
    latency = models.CharField(
        max_length=50,
        blank=True,
        help_text="Time taken to respond (SCORM format)"
    )
    
    # Additional data
    objectives = models.JSONField(
        default=list,
        help_text="Related objective IDs"
    )
    learner_response_data = models.JSONField(
        default=dict,
        help_text="Additional learner response data"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'scorm_interaction'
        verbose_name = 'SCORM Interaction'
        verbose_name_plural = 'SCORM Interactions'
        unique_together = ['attempt', 'interaction_id']
        ordering = ['timestamp', 'created_at']
    
    def __str__(self):
        return f"{self.attempt.user.username} - {self.interaction_id} ({self.interaction_type})"
    
    def get_latency_seconds(self):
        """Convert SCORM latency format to seconds"""
        if not self.latency:
            return 0
        
        try:
            if self.latency.startswith('PT'):
                # SCORM 2004 duration format
                return self._parse_iso_duration(self.latency)
            else:
                # SCORM 1.2 time format
                return self._parse_scorm_time(self.latency)
        except:
            return 0
    
    def _parse_scorm_time(self, time_str):
        """Parse SCORM time format (hhhh:mm:ss.ss) to seconds"""
        try:
            if not time_str:
                return 0
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            return 0
        except (ValueError, IndexError, TypeError):
            return 0
    
    def _parse_iso_duration(self, duration_str):
        """Parse ISO 8601 duration format (PT1H30M45S) to seconds"""
        try:
            if not duration_str or not duration_str.startswith('PT'):
                return 0
                
            duration_str = duration_str[2:]
            hours = 0
            minutes = 0
            seconds = 0
            
            if 'H' in duration_str:
                hours = int(duration_str.split('H')[0])
                duration_str = duration_str.split('H')[1]
            
            if 'M' in duration_str:
                minutes = int(duration_str.split('M')[0])
                duration_str = duration_str.split('M')[1]
            
            if 'S' in duration_str:
                seconds = float(duration_str.split('S')[0])
            
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError, TypeError):
            return 0


class ScormObjective(models.Model):
    """
    Model to track SCORM objectives and their completion status
    """
    SUCCESS_STATUS_CHOICES = [
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('completed', 'Completed'),
        ('incomplete', 'Incomplete'),
        ('browsed', 'Browsed'),
        ('not attempted', 'Not Attempted'),
    ]
    
    COMPLETION_STATUS_CHOICES = [
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('completed', 'Completed'),
        ('incomplete', 'Incomplete'),
        ('browsed', 'Browsed'),
        ('not attempted', 'Not Attempted'),
    ]
    
    attempt = models.ForeignKey(
        ScormAttempt,
        on_delete=models.CASCADE,
        related_name='objectives'
    )
    
    # Objective identification
    objective_id = models.CharField(
        max_length=255,
        help_text="Unique identifier for the objective"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the objective"
    )
    
    # Status tracking
    success_status = models.CharField(
        max_length=20,
        choices=SUCCESS_STATUS_CHOICES,
        default='not attempted',
        help_text="Success status of the objective"
    )
    completion_status = models.CharField(
        max_length=20,
        choices=COMPLETION_STATUS_CHOICES,
        default='not attempted',
        help_text="Completion status of the objective"
    )
    
    # Scoring
    score_raw = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Raw score for objective"
    )
    score_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=0,
        help_text="Minimum score for objective"
    )
    score_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=100,
        help_text="Maximum score for objective"
    )
    score_scaled = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Scaled score (0-1)"
    )
    
    # Progress tracking
    progress_measure = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Progress measure (0-1)"
    )
    
    # Additional data
    objective_data = models.JSONField(
        default=dict,
        help_text="Additional objective data"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'scorm_objective'
        verbose_name = 'SCORM Objective'
        verbose_name_plural = 'SCORM Objectives'
        unique_together = ['attempt', 'objective_id']
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.attempt.user.username} - {self.objective_id} ({self.success_status})"


class ScormComment(models.Model):
    """
    Model to track comments from learners and LMS
    """
    COMMENT_TYPE_CHOICES = [
        ('learner', 'Learner Comment'),
        ('lms', 'LMS Comment'),
    ]
    
    attempt = models.ForeignKey(
        ScormAttempt,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    
    # Comment identification
    comment_type = models.CharField(
        max_length=10,
        choices=COMMENT_TYPE_CHOICES,
        help_text="Type of comment"
    )
    comment_text = models.TextField(
        help_text="Comment content"
    )
    location = models.CharField(
        max_length=500,
        blank=True,
        help_text="Location where comment was made"
    )
    timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the comment was made"
    )
    
    # Additional data
    comment_data = models.JSONField(
        default=dict,
        help_text="Additional comment data"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'scorm_comment'
        verbose_name = 'SCORM Comment'
        verbose_name_plural = 'SCORM Comments'
        ordering = ['timestamp', 'created_at']
    
    def __str__(self):
        return f"{self.attempt.user.username} - {self.comment_type} comment"
    

