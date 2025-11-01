"""
SCORM Enrollment and Attempt Tracking Models
Proper tracking of SCORM learner enrollment, attempts, and complete CMI data
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from courses.models import Topic
from scorm.models import ScormPackage


class ScormEnrollment(models.Model):
    """
    Tracks a learner's enrollment in a SCORM topic/SCO
    One enrollment per user per topic, can have multiple attempts
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scorm_enrollments'
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name='scorm_enrollments',
        help_text="SCORM topic the learner is enrolled in"
    )
    package = models.ForeignKey(
        ScormPackage,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    
    # Enrollment metadata
    enrolled_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    
    # Aggregated status across all attempts
    total_attempts = models.IntegerField(default=0)
    best_score = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Best score across all attempts (raw score)"
    )
    first_completion_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date of first successful completion"
    )
    last_completion_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date of most recent completion"
    )
    
    # Overall enrollment status
    STATUS_CHOICES = [
        ('enrolled', 'Enrolled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('passed', 'Passed'),
    ]
    enrollment_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='enrolled'
    )
    
    # Total time across all attempts
    total_time_seconds = models.IntegerField(
        default=0,
        help_text="Total time spent across all attempts in seconds"
    )
    
    class Meta:
        unique_together = [['user', 'topic']]
        indexes = [
            models.Index(fields=['user', 'topic']),
            models.Index(fields=['enrollment_status']),
            models.Index(fields=['last_accessed']),
        ]
        ordering = ['-last_accessed']
    
    def __str__(self):
        return f"{self.user.username} - {self.topic.title} ({self.enrollment_status})"
    
    def create_new_attempt(self, session_id=None):
        """Create a new attempt for this enrollment"""
        import uuid
        self.total_attempts += 1
        self.save()
        
        # Generate session_id if not provided
        if session_id is None:
            session_id = uuid.uuid4()
        
        return ScormAttempt.objects.create(
            enrollment=self,
            user=self.user,
            topic=self.topic,
            package=self.package,
            attempt_number=self.total_attempts,
            session_id=session_id
        )
    
    def get_current_attempt(self):
        """Get the most recent active attempt"""
        return self.attempts.filter(
            completed=False
        ).order_by('-started_at').first()
    
    def update_best_score(self, score):
        """Update best score if this score is better"""
        if self.best_score is None or score > self.best_score:
            self.best_score = score
            self.save(update_fields=['best_score'])


class ScormAttempt(models.Model):
    """
    Tracks individual SCORM attempts/sessions
    Each launch creates a new attempt that tracks complete CMI data
    """
    enrollment = models.ForeignKey(
        ScormEnrollment,
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scorm_attempts'
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name='scorm_attempts'
    )
    package = models.ForeignKey(
        ScormPackage,
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    
    # Attempt identification
    attempt_number = models.IntegerField(
        help_text="Sequential attempt number for this enrollment"
    )
    session_id = models.UUIDField(
        unique=True,
        help_text="Unique session ID for this attempt"
    )
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    last_commit_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    completed = models.BooleanField(default=False)
    terminated = models.BooleanField(
        default=False,
        help_text="Whether LMSFinish/Terminate was called"
    )
    
    # SCORM version for this attempt
    scorm_version = models.CharField(
        max_length=10,
        choices=[('1.2', 'SCORM 1.2'), ('2004', 'SCORM 2004')],
        default='1.2'
    )
    
    # Score tracking
    score_raw = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True
    )
    score_min = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True
    )
    score_max = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True
    )
    score_scaled = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Scaled score (0-1 range) for SCORM 2004"
    )
    
    # Completion tracking
    completion_status = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="SCORM completion status: completed, incomplete, not attempted, unknown"
    )
    success_status = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="SCORM success status: passed, failed, unknown"
    )
    
    # Time tracking
    total_time = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="SCORM time format (e.g., PT1H23M45S)"
    )
    total_time_seconds = models.IntegerField(
        default=0,
        help_text="Total time in seconds for easier querying"
    )
    session_time = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Session time for this attempt (HH:MM:SS or PTnHnMnS)"
    )
    session_time_seconds = models.IntegerField(
        default=0,
        help_text="Session time in seconds for easier querying"
    )
    
    # Location/bookmark
    lesson_location = models.TextField(
        null=True,
        blank=True,
        help_text="Current location in SCO (SCORM 1.2) or cmi.location (2004)"
    )
    suspend_data = models.TextField(
        null=True,
        blank=True,
        help_text="Suspend data for resuming session"
    )
    
    # Entry/Exit
    entry_mode = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Entry mode: ab-initio, resume, (SCORM 1.2/2004)"
    )
    exit_mode = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Exit mode: time-out, suspend, logout, normal, (SCORM 1.2/2004)"
    )
    
    # Complete CMI data tree
    cmi_data = models.JSONField(
        default=dict,
        help_text="Complete SCORM CMI data tree as sent by SCO"
    )
    
    # Interaction tracking (objectives, interactions, comments)
    interactions_data = models.JSONField(
        default=list,
        help_text="All cmi.interactions.n data"
    )
    objectives_data = models.JSONField(
        default=list,
        help_text="All cmi.objectives.n data"
    )
    comments_from_learner = models.JSONField(
        default=list,
        help_text="Comments from learner (cmi.comments_from_learner)"
    )
    comments_from_lms = models.JSONField(
        default=list,
        help_text="Comments from LMS (cmi.comments_from_lms)"
    )
    
    # Commit tracking for debugging/auditing
    commit_count = models.IntegerField(
        default=0,
        help_text="Number of LMSCommit calls received"
    )
    last_sequence_number = models.IntegerField(
        default=0,
        help_text="Last sequence number for idempotency"
    )
    
    class Meta:
        unique_together = [['enrollment', 'attempt_number']]
        indexes = [
            models.Index(fields=['user', 'topic']),
            models.Index(fields=['session_id']),
            models.Index(fields=['enrollment', 'attempt_number']),
            models.Index(fields=['completed', 'started_at']),
            models.Index(fields=['user', 'completed']),
        ]
        ordering = ['-started_at']
    
    def __str__(self):
        return (
            f"Attempt {self.attempt_number} - {self.user.username} - "
            f"{self.topic.title} ({self.get_status_display()})"
        )
    
    def get_status_display(self):
        """Human-readable status"""
        if self.completed:
            if self.success_status == 'passed':
                return "Passed"
            elif self.success_status == 'failed':
                return "Failed"
            elif self.completion_status == 'completed':
                return "Completed"
        return "In Progress"
    
    def update_from_cmi_data(self, cmi_data_dict, scorm_version='1.2'):
        """
        Update attempt from raw CMI data
        
        Args:
            cmi_data_dict: Dictionary of CMI elements (e.g., {'cmi.core.score.raw': 85})
            scorm_version: '1.2' or '2004'
        """
        from scorm.utils import parse_scorm_time
        from core.utils.type_guards import safe_get_float, safe_get_string
        
        # Store complete CMI tree
        self.cmi_data = cmi_data_dict
        self.scorm_version = scorm_version
        
        # Extract and normalize based on version
        if scorm_version == '1.2':
            self.score_raw = safe_get_float(cmi_data_dict, 'cmi.core.score.raw')
            self.score_min = safe_get_float(cmi_data_dict, 'cmi.core.score.min')
            self.score_max = safe_get_float(cmi_data_dict, 'cmi.core.score.max')
            self.completion_status = safe_get_string(cmi_data_dict, 'cmi.core.lesson_status')
            # SCORM 1.2 doesn't have separate success_status - it uses lesson_status values (passed/completed/failed)
            self.success_status = None
            self.total_time = safe_get_string(cmi_data_dict, 'cmi.core.total_time')
            self.session_time = safe_get_string(cmi_data_dict, 'cmi.core.session_time')
            self.lesson_location = safe_get_string(cmi_data_dict, 'cmi.core.lesson_location')
            self.suspend_data = safe_get_string(cmi_data_dict, 'cmi.suspend_data')
            self.entry_mode = safe_get_string(cmi_data_dict, 'cmi.core.entry')
            self.exit_mode = safe_get_string(cmi_data_dict, 'cmi.core.exit')
        else:  # SCORM 2004
            self.score_raw = safe_get_float(cmi_data_dict, 'cmi.score.raw')
            self.score_min = safe_get_float(cmi_data_dict, 'cmi.score.min')
            self.score_max = safe_get_float(cmi_data_dict, 'cmi.score.max')
            self.score_scaled = safe_get_float(cmi_data_dict, 'cmi.score.scaled')
            self.completion_status = safe_get_string(cmi_data_dict, 'cmi.completion_status')
            self.success_status = safe_get_string(cmi_data_dict, 'cmi.success_status')
            self.total_time = safe_get_string(cmi_data_dict, 'cmi.total_time')
            self.session_time = safe_get_string(cmi_data_dict, 'cmi.session_time')
            self.lesson_location = safe_get_string(cmi_data_dict, 'cmi.location')
            self.suspend_data = safe_get_string(cmi_data_dict, 'cmi.suspend_data')
            self.entry_mode = safe_get_string(cmi_data_dict, 'cmi.entry')
            self.exit_mode = safe_get_string(cmi_data_dict, 'cmi.exit')
        
        # Parse time to seconds
        if self.total_time:
            self.total_time_seconds = int(parse_scorm_time(self.total_time, scorm_version))
        if self.session_time:
            self.session_time_seconds = int(parse_scorm_time(self.session_time, scorm_version))
        
        # Extract interactions, objectives, comments
        self.interactions_data = self._extract_interactions(cmi_data_dict, scorm_version)
        self.objectives_data = self._extract_objectives(cmi_data_dict, scorm_version)
        self.comments_from_learner = self._extract_comments_learner(cmi_data_dict, scorm_version)
        
        # Update commit tracking
        self.commit_count += 1
        self.last_commit_at = timezone.now()
        
        # Check if completed
        if self.completion_status in ['completed', 'passed'] or self.success_status == 'passed':
            if not self.completed:
                self.completed = True
                self.completed_at = timezone.now()
                
                # Update enrollment
                self.enrollment.update_best_score(self.score_raw)
                if not self.enrollment.first_completion_date:
                    self.enrollment.first_completion_date = self.completed_at
                self.enrollment.last_completion_date = self.completed_at
                self.enrollment.enrollment_status = 'completed'
                self.enrollment.save()
        
        self.save()
    
    def _extract_interactions(self, cmi_data, version):
        """Extract all cmi.interactions.n.* data"""
        interactions = []
        if version == '1.2':
            prefix = 'cmi.interactions.'
        else:
            prefix = 'cmi.interactions.'
        
        # Group by interaction index
        interaction_indices = set()
        for key in cmi_data.keys():
            if key.startswith(prefix) and key != prefix + '_count':
                parts = key.replace(prefix, '').split('.')
                if parts and parts[0].isdigit():
                    interaction_indices.add(int(parts[0]))
        
        for idx in sorted(interaction_indices):
            interaction = {}
            for key, value in cmi_data.items():
                if key.startswith(f"{prefix}{idx}."):
                    field = key.replace(f"{prefix}{idx}.", '')
                    interaction[field] = value
            if interaction:
                interaction['index'] = idx
                interactions.append(interaction)
        
        return interactions
    
    def _extract_objectives(self, cmi_data, version):
        """Extract all cmi.objectives.n.* data"""
        objectives = []
        if version == '1.2':
            prefix = 'cmi.objectives.'
        else:
            prefix = 'cmi.objectives.'
        
        objective_indices = set()
        for key in cmi_data.keys():
            if key.startswith(prefix) and key != prefix + '_count':
                parts = key.replace(prefix, '').split('.')
                if parts and parts[0].isdigit():
                    objective_indices.add(int(parts[0]))
        
        for idx in sorted(objective_indices):
            objective = {}
            for key, value in cmi_data.items():
                if key.startswith(f"{prefix}{idx}."):
                    field = key.replace(f"{prefix}{idx}.", '')
                    objective[field] = value
            if objective:
                objective['index'] = idx
                objectives.append(objective)
        
        return objectives
    
    def _extract_comments_learner(self, cmi_data, version):
        """Extract learner comments"""
        comments = []
        if version == '1.2':
            # SCORM 1.2: cmi.comments is a single string
            if 'cmi.comments' in cmi_data:
                comments.append({'comment': cmi_data['cmi.comments']})
        else:
            # SCORM 2004: cmi.comments_from_learner.n.*
            prefix = 'cmi.comments_from_learner.'
            comment_indices = set()
            for key in cmi_data.keys():
                if key.startswith(prefix) and key != prefix + '_count':
                    parts = key.replace(prefix, '').split('.')
                    if parts and parts[0].isdigit():
                        comment_indices.add(int(parts[0]))
            
            for idx in sorted(comment_indices):
                comment = {}
                for key, value in cmi_data.items():
                    if key.startswith(f"{prefix}{idx}."):
                        field = key.replace(f"{prefix}{idx}.", '')
                        comment[field] = value
                if comment:
                    comment['index'] = idx
                    comments.append(comment)
        
        return comments


class ScormCommitLog(models.Model):
    """
    Audit log of every SCORM commit for debugging and compliance
    Optional - enable for detailed auditing
    """
    attempt = models.ForeignKey(
        ScormAttempt,
        on_delete=models.CASCADE,
        related_name='commit_logs'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    sequence_number = models.IntegerField()
    
    # Snapshot of CMI data at this commit
    cmi_snapshot = models.JSONField()
    
    # What changed since last commit
    changes = models.JSONField(
        default=dict,
        help_text="Dictionary of changed CMI elements"
    )
    
    # Client metadata
    client_timestamp = models.CharField(max_length=50, null=True, blank=True)
    user_agent = models.CharField(max_length=500, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['attempt', 'sequence_number']),
            models.Index(fields=['timestamp']),
        ]
        ordering = ['sequence_number']
    
    def __str__(self):
        return f"Commit {self.sequence_number} - Attempt {self.attempt.attempt_number}"


