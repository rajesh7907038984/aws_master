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
        ('1.2', 'SCORM 1.2'),
        ('2004', 'SCORM 2004'),
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
    
    # Time tracking
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
    
    # Location tracking (for resume)
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
    
    # Full SCORM data storage
    cmi_data = models.JSONField(
        default=dict,
        help_text="Complete CMI data model storage"
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
    

