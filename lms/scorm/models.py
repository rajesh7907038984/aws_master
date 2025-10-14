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
    Simplified SCORM attempt model following global standards
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
    
    # Basic attempt tracking
    attempt_number = models.IntegerField(default=1)
    
    # Core SCORM data model elements
    lesson_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='not_attempted'
    )
    completion_status = models.CharField(max_length=20, default='incomplete')
    success_status = models.CharField(max_length=20, default='unknown')
    
    # Basic score tracking
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
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Scaled score (0-1 range)"
    )
    
    # Basic time tracking
    total_time = models.CharField(
        max_length=50,
        default='0000:00:00.00',
        help_text="Total time in SCORM format"
    )
    session_time = models.CharField(
        max_length=50,
        default='0000:00:00.00',
        help_text="Session time in SCORM format"
    )
    
    # Basic location and progress
    lesson_location = models.CharField(
        max_length=1000,
        blank=True,
        help_text="Bookmark/location in the course"
    )
    suspend_data = models.TextField(
        blank=True,
        help_text="Suspend data for resuming"
    )
    
    # Basic SCORM data
    entry = models.CharField(
        max_length=20,
        default='ab-initio',
        help_text="Entry mode (ab-initio, resume)"
    )
    exit_mode = models.CharField(max_length=20, blank=True)
    
    # Core CMI data storage
    cmi_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="SCORM CMI data model storage"
    )
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Additional tracking fields for enhanced SCORM tracking
    completed_slides = models.JSONField(default=dict, blank=True)
    detailed_tracking = models.JSONField(default=dict, blank=True)
    last_visited_slide = models.CharField(max_length=255, default='', blank=True)
    navigation_history = models.JSONField(default=list, blank=True)
    progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        blank=True
    )
    session_data = models.JSONField(default=dict, blank=True)
    session_start_time = models.DateTimeField(null=True, blank=True)
    session_end_time = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.IntegerField(default=0, blank=True)
    total_slides = models.IntegerField(default=0, blank=True)
    
    class Meta:
        db_table = 'scorm_attempt'
        verbose_name = 'SCORM Attempt'
        verbose_name_plural = 'SCORM Attempts'
        unique_together = ['user', 'scorm_package', 'attempt_number']
        ordering = ['-started_at']
    
    def save(self, *args, **kwargs):
        """Initialize JSON fields if None"""
        self.cmi_data = self.cmi_data or {}
        self.completed_slides = self.completed_slides or {}
        self.detailed_tracking = self.detailed_tracking or {}
        self.navigation_history = self.navigation_history or []
        self.session_data = self.session_data or {}
        super().save(*args, **kwargs)
    
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


# Simplified SCORM models - removed complex interaction and objective tracking
# These are not essential for basic SCORM functionality and add unnecessary complexity
    

