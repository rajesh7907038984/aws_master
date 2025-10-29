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
    
    has_score_requirement = models.BooleanField(
        default=True,
        help_text="Whether this SCORM content requires a passing score to be marked complete"
    )
    
    # Enhanced package management fields
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]
    
    EXTRACT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('extracted', 'Extracted'),
        ('failed', 'Failed'),
    ]
    
    RUNTIME_API_CHOICES = [
        ('scorm_1_2', 'SCORM 1.2'),
        ('scorm_2004', 'SCORM 2004'),
        ('xapi', 'xAPI'),
        ('cmi5', 'CMI5'),
    ]
    
    LMS_LAUNCH_TYPE_CHOICES = [
        ('iframe', 'Iframe'),
        ('new_window', 'New Window'),
        ('popup', 'Popup'),
    ]
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        help_text="Control whether a SCORM package is live or hidden"
    )
    
    size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Store ZIP file size for quick lookup or quota management"
    )
    
    entry_point = models.CharField(
        max_length=800,
        blank=True,
        help_text="Sometimes different from launch_url; identifies SCO start file from manifest"
    )
    
    organization = models.CharField(
        max_length=800,
        blank=True,
        help_text="imsmanifest.xml may define multiple organizations; this stores the one used"
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional manifest-level metadata (duration, keywords, vendor info, etc.)"
    )
    
    is_multi_sco = models.BooleanField(
        default=False,
        help_text="Indicates if the package has multiple SCOs (vs. a single SCO course)"
    )
    
    extract_status = models.CharField(
        max_length=20,
        choices=EXTRACT_STATUS_CHOICES,
        default='pending',
        help_text="Useful for async extraction or background processing"
    )
    
    runtime_api = models.CharField(
        max_length=20,
        choices=RUNTIME_API_CHOICES,
        default='scorm_1_2',
        help_text="Helps the player select the correct runtime handler"
    )
    
    lms_launch_type = models.CharField(
        max_length=20,
        choices=LMS_LAUNCH_TYPE_CHOICES,
        default='iframe',
        help_text="Controls how the course is displayed"
    )
    
    duration_estimate = models.DurationField(
        null=True,
        blank=True,
        help_text="Optional — can be extracted from metadata or author-provided"
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Track which admin or instructor uploaded it"
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
    )
    score_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
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
        blank=True,
        help_text="Total time in SCORM format (hhhh:mm:ss.ss)"
    )
    session_time = models.CharField(
        max_length=50,
        blank=True,
        help_text="Session time in SCORM format"
    )
    # Additional time tracking fields
    time_spent_seconds = models.IntegerField(
        null=True,
        blank=True,
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
    
    # SCORM 1.2 Additional CMI Fields
    cmi_student_preferences = models.JSONField(
        default=dict,
        blank=True,
        help_text="SCORM 1.2 student preferences (audio, language, speed, text)"
    )
    cmi_objectives_12 = models.JSONField(
        default=list,
        blank=True,
        help_text="SCORM 1.2 objectives data with scores and status"
    )
    cmi_interactions_12 = models.JSONField(
        default=list,
        blank=True,
        help_text="SCORM 1.2 interactions data with responses and results"
    )
    
    # SCORM 2004 Additional CMI Fields
    cmi_comments_from_learner = models.JSONField(
        default=list,
        blank=True,
        help_text="SCORM 2004 learner comments with timestamps and locations"
    )
    cmi_comments_from_lms = models.JSONField(
        default=list,
        blank=True,
        help_text="SCORM 2004 LMS comments with timestamps and locations"
    )
    cmi_objectives_2004 = models.JSONField(
        default=list,
        blank=True,
        help_text="SCORM 2004 objectives data with progress measures and status"
    )
    cmi_interactions_2004 = models.JSONField(
        default=list,
        blank=True,
        help_text="SCORM 2004 interactions data with enhanced tracking"
    )
    
    # xAPI Event Data Fields
    xapi_events = models.JSONField(
        default=list,
        blank=True,
        help_text="xAPI event statements array"
    )
    xapi_actor = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI actor data (name, mbox, etc.)"
    )
    xapi_verb = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI verb data (id, display)"
    )
    xapi_object = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI object data (id, definition)"
    )
    xapi_result = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI result data (score, success, completion, duration)"
    )
    xapi_context = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI context data (registration, activities, extensions)"
    )
    xapi_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="xAPI event timestamp"
    )
    xapi_stored = models.DateTimeField(
        null=True,
        blank=True,
        help_text="xAPI stored timestamp"
    )
    xapi_authority = models.JSONField(
        default=dict,
        blank=True,
        help_text="xAPI authority data"
    )
    xapi_version = models.CharField(
        max_length=10,
        default='1.0.3',
        blank=True,
        help_text="xAPI version"
    )
    xapi_attachments = models.JSONField(
        default=list,
        blank=True,
        help_text="xAPI attachments array"
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
        # Simple defaults based on SCORM version
        defaults = {
            'cmi.core.lesson_status': 'not attempted',
            'cmi.completion_status': 'not attempted',
            'cmi.success_status': 'unknown',
            'cmi.core.entry': 'ab-initio',
        }
        return defaults.get(field, '')
    
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
        
        # Ensure CMI data fields are never None
        if self.cmi_data is None:
            self.cmi_data = {}
        if self.cmi_data_history is None:
            self.cmi_data_history = []
        
        # Ensure SCORM 1.2 fields are properly initialized
        if self.cmi_student_preferences is None:
            self.cmi_student_preferences = {}
        if self.cmi_objectives_12 is None:
            self.cmi_objectives_12 = []
        if self.cmi_interactions_12 is None:
            self.cmi_interactions_12 = []
        
        # Ensure SCORM 2004 fields are properly initialized
        if self.cmi_comments_from_learner is None:
            self.cmi_comments_from_learner = []
        if self.cmi_comments_from_lms is None:
            self.cmi_comments_from_lms = []
        if self.cmi_objectives_2004 is None:
            self.cmi_objectives_2004 = []
        if self.cmi_interactions_2004 is None:
            self.cmi_interactions_2004 = []
        
        # Ensure xAPI fields are properly initialized
        if self.xapi_events is None:
            self.xapi_events = []
        if self.xapi_actor is None:
            self.xapi_actor = {}
        if self.xapi_verb is None:
            self.xapi_verb = {}
        if self.xapi_object is None:
            self.xapi_object = {}
        if self.xapi_result is None:
            self.xapi_result = {}
        if self.xapi_context is None:
            self.xapi_context = {}
        if self.xapi_authority is None:
            self.xapi_authority = {}
        if self.xapi_attachments is None:
            self.xapi_attachments = []
    
    def is_passed(self):
        """Check if attempt is passed based on mastery score"""
        if self.scorm_package.mastery_score and self.score_raw is not None:
            return self.score_raw >= self.scorm_package.mastery_score
        return self.lesson_status in ['passed', 'completed']
    
    def get_scorm_version_fields(self):
        """Get the appropriate CMI fields based on SCORM version"""
        if self.scorm_package.version == '1.2':
            return {
                'objectives': self.cmi_objectives_12,
                'interactions': self.cmi_interactions_12,
                'student_preferences': self.cmi_student_preferences,
            }
        else:  # SCORM 2004
            return {
                'objectives': self.cmi_objectives_2004,
                'interactions': self.cmi_interactions_2004,
                'comments_from_learner': self.cmi_comments_from_learner,
                'comments_from_lms': self.cmi_comments_from_lms,
            }
    
    def add_xapi_event(self, event_data):
        """Add an xAPI event to the events array"""
        if not isinstance(self.xapi_events, list):
            self.xapi_events = []
        
        # Add timestamp if not provided
        if 'timestamp' not in event_data:
            event_data['timestamp'] = timezone.now().isoformat()
        
        self.xapi_events.append(event_data)
    
    def get_latest_xapi_event(self):
        """Get the most recent xAPI event"""
        if not self.xapi_events:
            return None
        return self.xapi_events[-1]
    
    def update_xapi_actor(self, actor_data):
        """Update xAPI actor information"""
        self.xapi_actor.update(actor_data)
    
    def update_xapi_result(self, result_data):
        """Update xAPI result information"""
        self.xapi_result.update(result_data)


