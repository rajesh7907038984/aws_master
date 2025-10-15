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
        return "{} ({})".format(self.title, self.version)


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
    
    # Basic tracking fields only
    
    class Meta:
        db_table = 'scorm_attempt'
        verbose_name = 'SCORM Attempt'
        verbose_name_plural = 'SCORM Attempts'
        unique_together = ['user', 'scorm_package', 'attempt_number']
        ordering = ['-started_at']
    
    def clean(self):
        """Validate SCORM attempt data"""
        from decimal import Decimal
        from django.core.exceptions import ValidationError
        
        super().clean()
        
        # Validate score fields
        if self.score_raw is not None:
            try:
                raw_score = Decimal(str(self.score_raw))
                if raw_score < 0:
                    raise ValidationError({'score_raw': 'Raw score cannot be negative'})
            except (ValueError, TypeError):
                raise ValidationError({'score_raw': 'Invalid raw score format'})
        
        if self.score_min is not None and self.score_max is not None:
            try:
                min_score = Decimal(str(self.score_min))
                max_score = Decimal(str(self.score_max))
                if min_score >= max_score:
                    raise ValidationError({
                        'score_min': 'Minimum score must be less than maximum score'
                    })
            except (ValueError, TypeError):
                raise ValidationError({'score_min': 'Invalid score range format'})
        
        # Validate scaled score is between 0 and 1
        if self.score_scaled is not None:
            try:
                scaled_score = Decimal(str(self.score_scaled))
                if scaled_score < 0 or scaled_score > 1:
                    raise ValidationError({
                        'score_scaled': 'Scaled score must be between 0 and 1'
                    })
            except (ValueError, TypeError):
                raise ValidationError({'score_scaled': 'Invalid scaled score format'})
        
        # Validate time format (SCORM format: HH:MM:SS.SS)
        if self.total_time and self.total_time != '0000:00:00.00':
            import re
            time_pattern = r'^\d{4}:\d{2}:\d{2}\.\d{2}$'
            if not re.match(time_pattern, self.total_time):
                raise ValidationError({
                    'total_time': 'Time must be in SCORM format (HHHH:MM:SS.SS)'
                })
        
        # Validate lesson status
        valid_statuses = [choice[0] for choice in self.STATUS_CHOICES]
        if self.lesson_status not in valid_statuses:
            raise ValidationError({
                'lesson_status': f'Invalid lesson status. Must be one of: {valid_statuses}'
            })
        
        # Validate attempt number
        if self.attempt_number < 1:
            raise ValidationError({
                'attempt_number': 'Attempt number must be at least 1'
            })
    
    def save(self, *args, **kwargs):
        """Simple save method"""
        self.cmi_data = self.cmi_data or {}
        from django.utils import timezone
        self.last_accessed = timezone.now()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return "{} - {} - Attempt {}".format(self.user.username, self.scorm_package.title, self.attempt_number)
    
    def get_percentage_score(self):
        """Calculate percentage score using Decimal for precision"""
        from decimal import Decimal, ROUND_HALF_UP
        
        if self.score_raw is not None and self.score_max:
            try:
                raw_score = Decimal(str(self.score_raw))
                max_score = Decimal(str(self.score_max))
                
                if max_score == 0:
                    return None
                
                percentage = (raw_score / max_score) * Decimal('100')
                return percentage.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except (ValueError, TypeError, ZeroDivisionError):
                return None
        return None
    
    def is_passed(self):
        """Check if attempt is passed based on mastery score"""
        if self.scorm_package.mastery_score and self.score_raw is not None:
            return self.score_raw >= self.scorm_package.mastery_score
        return self.lesson_status in ['passed', 'completed']
    
    def update_tracking_data(self, element, value):
        """Simple tracking data update"""
        if not self.cmi_data:
            self.cmi_data = {}
        self.cmi_data[element] = value
        
        # Update basic fields
        if element == 'cmi.core.lesson_status':
            self.lesson_status = value
        elif element == 'cmi.completion_status':
            self.completion_status = value
        elif element == 'cmi.success_status':
            self.success_status = value
        elif element in ['cmi.core.lesson_location', 'cmi.location']:
            self.lesson_location = value
        elif element == 'cmi.suspend_data':
            self.suspend_data = value
        
        self.save()
        return True


# Simplified SCORM models - removed complex interaction and objective tracking
# These are not essential for basic SCORM functionality and add unnecessary complexity
    

