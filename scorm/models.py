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
    identifier = models.CharField(max_length=800, help_text="Package identifier from manifest")
    title = models.CharField(max_length=800, blank=True)
    description = models.TextField(blank=True)
    
    # Package file storage
    package_file = models.FileField(
        upload_to='scorm_packages/%Y/%m/',
        max_length=800,
        help_text="Original SCORM ZIP package"
    )
    extracted_path = models.CharField(
        max_length=800,
        help_text="Path to extracted SCORM content"
    )
    
    # Launch information
    launch_url = models.CharField(
        max_length=800,
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
    
    def get_correct_launch_url(self):
        """
        Get the correct launch URL, preferring SCORM API wrapper files over content files.
        This helps fix packages that were incorrectly configured with story.html instead of index_lms.html.
        """
        from django.core.files.storage import default_storage
        
        # If already using a SCORM API wrapper, return as-is
        if self.launch_url and any(wrapper in self.launch_url.lower() for wrapper in ['index_lms.html', 'indexapi.html', 'lms.html', 'scorm.html']):
            return self.launch_url
        
        # Check if indexAPI.html exists specifically
        scorm_api_wrappers = ['indexAPI.html']
        for wrapper in scorm_api_wrappers:
            wrapper_path = f"{self.extracted_path}/{wrapper}"
            if default_storage.exists(wrapper_path):
                return wrapper
        
        # Fallback to current launch URL
        return self.launch_url
    
    def fix_launch_url(self):
        """
        Fix the launch URL if it's pointing to a content file instead of SCORM API wrapper.
        Returns True if the launch URL was updated.
        """
        correct_url = self.get_correct_launch_url()
        if correct_url != self.launch_url:
            self.launch_url = correct_url
            self.save()
            return True
        return False
    
    def get_package_type(self):
        """
        Determine if this is quiz-based or slide-based SCORM
        Returns: 'quiz_based', 'slide_based', or 'unknown'
        """
        # Check version field first
        if self.version in ['captivate', 'lectora', 'ispring']:
            return 'quiz_based'
        elif self.version == 'storyline':
            return 'slide_based'
        
        # Check manifest data for indicators
        if self.manifest_data:
            manifest_text = str(self.manifest_data).lower()
            
            # Quiz-based indicators
            quiz_indicators = ['quiz', 'assessment', 'test', 'question', 'captivate', 'lectora']
            if any(indicator in manifest_text for indicator in quiz_indicators):
                return 'quiz_based'
            
            # Slide-based indicators
            slide_indicators = ['storyline', 'slide', 'scene', 'story.html']
            if any(indicator in manifest_text for indicator in slide_indicators):
                return 'slide_based'
        
        # Check launch URL
        if self.launch_url:
            launch_lower = self.launch_url.lower()
            if 'story.html' in launch_lower or 'storyline' in launch_lower:
                return 'slide_based'
            elif 'quiz' in launch_lower or 'assessment' in launch_lower:
                return 'quiz_based'
        
        return 'unknown'
    
    def is_slide_based(self):
        """Check if this is a slide-based SCORM package"""
        return self.get_package_type() == 'slide_based'
    
    def is_quiz_based(self):
        """Check if this is a quiz-based SCORM package"""
        return self.get_package_type() == 'quiz_based'


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
        max_length=800,
        blank=True,
        help_text="Last visited slide/page identifier"
    )
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Progress percentage (0-100)"
    )
    navigation_history = models.JSONField(
        default=list,
        blank=True,
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
    # CMI data history tracking
    cmi_data_history = models.JSONField(
        default=list,
        blank=True,
        help_text="Complete history of CMI data changes with timestamps"
    )
    # Additional tracking data
    detailed_tracking = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed tracking data including slide visits, time per slide, etc."
    )
    session_data = models.JSONField(
        default=dict,
        blank=True,
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
    
    def get_schema_default(self, field):
        """Get schema-defined default value for a field based on SCORM version"""
        from .cmi_data_handler import CMIDataHandler
        return CMIDataHandler.get_schema_default(field, self.scorm_package.version)
    
    def get_proper_defaults(self):
        """Get proper schema-defined defaults for all SCORM fields"""
        return {
            'lesson_status': self.get_schema_default('cmi.core.lesson_status'),
            'completion_status': self.get_schema_default('cmi.completion_status'),
            'success_status': self.get_schema_default('cmi.success_status'),
            'entry': self.get_schema_default('cmi.core.entry'),
        }
    
    def __str__(self):
        return f"{self.user.username} - {self.scorm_package.title} - Attempt {self.attempt_number}"
    
    def get_percentage_score(self):
        """Calculate percentage score"""
        if self.score_raw is not None and self.score_max:
            return (float(self.score_raw) / float(self.score_max)) * 100
        return None
    
    def clean(self):
        """Custom validation to ensure JSON fields are properly initialized"""
        super().clean()
        
        # Ensure JSON fields are never None
        if self.navigation_history is None:
            self.navigation_history = []
        if self.detailed_tracking is None:
            self.detailed_tracking = {}
        if self.session_data is None:
            self.session_data = {}
        if self.cmi_data is None:
            self.cmi_data = {}
        if self.cmi_data_history is None:
            self.cmi_data_history = []
    
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
        max_length=800,
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
        max_length=800,
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
        max_length=800,
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
    

