import json
import uuid
from datetime import datetime
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import URLValidator
from users.models import CustomUser


class LRS(models.Model):
    """Learning Record Store configuration"""
    name = models.CharField(max_length=255, unique=True)
    endpoint = models.URLField(validators=[URLValidator()])
    version = models.CharField(max_length=20, default='1.0.3')
    username = models.CharField(max_length=255, blank=True)
    password = models.CharField(max_length=255, blank=True)
    api_key = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Learning Record Store"
        verbose_name_plural = "Learning Record Stores"
    
    def __str__(self):
        return self.name


class Statement(models.Model):
    """xAPI Statement storage"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    statement_id = models.CharField(max_length=500, unique=True)
    
    # Actor (who performed the action)
    actor_type = models.CharField(max_length=20, choices=[
        ('Agent', 'Agent'),
        ('Group', 'Group')
    ])
    actor_mbox = models.EmailField(blank=True)
    actor_mbox_sha1sum = models.CharField(max_length=40, blank=True)
    actor_openid = models.URLField(blank=True)
    actor_account_homepage = models.URLField(blank=True)
    actor_account_name = models.CharField(max_length=255, blank=True)
    actor_name = models.CharField(max_length=255, blank=True)
    
    # Verb (what action was performed)
    verb_id = models.URLField()
    verb_display = models.JSONField(default=dict)
    
    # Object (what was acted upon)
    object_type = models.CharField(max_length=20, choices=[
        ('Activity', 'Activity'),
        ('Agent', 'Agent'),
        ('Group', 'Group'),
        ('StatementRef', 'StatementRef'),
        ('SubStatement', 'SubStatement')
    ])
    object_id = models.URLField()
    object_definition_name = models.JSONField(default=dict)
    object_definition_description = models.JSONField(default=dict)
    object_definition_type = models.URLField(blank=True)
    object_definition_more_info = models.URLField(blank=True)
    object_definition_interaction_type = models.CharField(max_length=50, blank=True)
    object_definition_correct_responses_pattern = models.JSONField(default=list)
    object_definition_choices = models.JSONField(default=list)
    object_definition_scale = models.JSONField(default=list)
    object_definition_source = models.JSONField(default=list)
    object_definition_target = models.JSONField(default=list)
    object_definition_steps = models.JSONField(default=list)
    object_definition_extensions = models.JSONField(default=dict)
    
    # Result (outcome of the action)
    result_score_scaled = models.FloatField(null=True, blank=True)
    result_score_raw = models.FloatField(null=True, blank=True)
    result_score_min = models.FloatField(null=True, blank=True)
    result_score_max = models.FloatField(null=True, blank=True)
    result_success = models.BooleanField(null=True, blank=True)
    result_completion = models.BooleanField(null=True, blank=True)
    result_response = models.TextField(blank=True)
    result_duration = models.DurationField(null=True, blank=True)
    result_extensions = models.JSONField(default=dict)
    
    # Context (additional information)
    context_registration = models.UUIDField(null=True, blank=True)
    context_instructor = models.JSONField(default=dict)
    context_team = models.JSONField(default=dict)
    context_context_activities_parent = models.JSONField(default=list)
    context_context_activities_grouping = models.JSONField(default=list)
    context_context_activities_category = models.JSONField(default=list)
    context_context_activities_other = models.JSONField(default=list)
    context_revision = models.CharField(max_length=255, blank=True)
    context_platform = models.CharField(max_length=255, blank=True)
    context_language = models.CharField(max_length=10, blank=True)
    context_statement = models.JSONField(default=dict)
    context_extensions = models.JSONField(default=dict)
    
    # Timestamp and authority
    timestamp = models.DateTimeField(default=timezone.now)
    stored = models.DateTimeField(auto_now_add=True)
    authority = models.JSONField(default=dict)
    
    # Version and attachments
    version = models.CharField(max_length=20, default='1.0.3')
    attachments = models.JSONField(default=list)
    
    # Raw statement for complete storage
    raw_statement = models.JSONField(default=dict)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['actor_mbox', 'timestamp']),
            models.Index(fields=['object_id', 'timestamp']),
            models.Index(fields=['verb_id', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.actor_name} {self.verb_display.get('en-US', '')} {self.object_definition_name.get('en-US', '')}"


class ActivityProfile(models.Model):
    """xAPI Activity Profile storage"""
    activity_id = models.URLField()
    profile_id = models.CharField(max_length=255)
    content = models.JSONField(default=dict)
    content_type = models.CharField(max_length=100, default='application/json')
    etag = models.CharField(max_length=100)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['activity_id', 'profile_id']
        indexes = [
            models.Index(fields=['activity_id']),
            models.Index(fields=['profile_id']),
        ]
    
    def __str__(self):
        return f"Profile {self.profile_id} for {self.activity_id}"


class AgentProfile(models.Model):
    """xAPI Agent Profile storage"""
    agent = models.JSONField(default=dict)
    profile_id = models.CharField(max_length=255)
    content = models.JSONField(default=dict)
    content_type = models.CharField(max_length=100, default='application/json')
    etag = models.CharField(max_length=100)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['agent', 'profile_id']
        indexes = [
            models.Index(fields=['agent']),
            models.Index(fields=['profile_id']),
        ]
    
    def __str__(self):
        return f"Agent Profile {self.profile_id}"


class State(models.Model):
    """xAPI State storage"""
    activity_id = models.URLField()
    agent = models.JSONField(default=dict)
    state_id = models.CharField(max_length=255)
    registration = models.UUIDField(null=True, blank=True)
    content = models.JSONField(default=dict)
    content_type = models.CharField(max_length=100, default='application/json')
    etag = models.CharField(max_length=100)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['activity_id', 'agent', 'state_id', 'registration']
        indexes = [
            models.Index(fields=['activity_id']),
            models.Index(fields=['agent']),
            models.Index(fields=['state_id']),
        ]
    
    def __str__(self):
        return f"State {self.state_id} for {self.activity_id}"


class CMI5AU(models.Model):
    """cmi5 Assignable Unit"""
    au_id = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    launch_url = models.URLField()
    launch_parameters = models.JSONField(default=dict)
    mastery_score = models.FloatField(null=True, blank=True)
    move_on = models.CharField(max_length=20, choices=[
        ('Passed', 'Passed'),
        ('Completed', 'Completed'),
        ('CompletedAndPassed', 'Completed and Passed'),
        ('NotApplicable', 'Not Applicable')
    ], default='Completed')
    launch_method = models.CharField(max_length=20, choices=[
        ('AnyWindow', 'Any Window'),
        ('OwnWindow', 'Own Window'),
        ('NewWindow', 'New Window')
    ], default='AnyWindow')
    launch_parameters = models.JSONField(default=dict)
    au_metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "cmi5 Assignable Unit"
        verbose_name_plural = "cmi5 Assignable Units"
    
    def __str__(self):
        return self.title


class CMI5Registration(models.Model):
    """cmi5 Registration"""
    registration_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    au = models.ForeignKey(CMI5AU, on_delete=models.CASCADE)
    learner = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    course_id = models.CharField(max_length=255)
    launch_token = models.CharField(max_length=500, unique=True)
    launch_url = models.URLField()
    launch_parameters = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['au', 'learner', 'course_id']
        indexes = [
            models.Index(fields=['learner']),
            models.Index(fields=['au']),
            models.Index(fields=['course_id']),
        ]
    
    def __str__(self):
        return f"Registration for {self.learner.username} - {self.au.title}"


class CMI5Session(models.Model):
    """cmi5 Session tracking"""
    registration = models.ForeignKey(CMI5Registration, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=255, unique=True)
    launch_time = models.DateTimeField()
    exit_time = models.DateTimeField(null=True, blank=True)
    session_time = models.DurationField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['registration']),
            models.Index(fields=['session_id']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"Session {self.session_id} for {self.registration}"


class SCORM2004Sequencing(models.Model):
    """SCORM 2004 Sequencing Rules"""
    activity_id = models.CharField(max_length=255, unique=True)
    parent_id = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Sequencing rules
    sequencing_rules = models.JSONField(default=dict)
    rollup_rules = models.JSONField(default=dict)
    navigation_rules = models.JSONField(default=dict)
    
    # Objectives
    objectives = models.JSONField(default=dict)
    objective_rollup_rules = models.JSONField(default=dict)
    
    # Completion and success criteria
    completion_threshold = models.FloatField(null=True, blank=True)
    mastery_score = models.FloatField(null=True, blank=True)
    
    # Prerequisites
    prerequisites = models.JSONField(default=dict)
    
    # Delivery controls
    delivery_controls = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "SCORM 2004 Sequencing"
        verbose_name_plural = "SCORM 2004 Sequencing Rules"
    
    def __str__(self):
        return f"Sequencing for {self.activity_id}"


class SCORM2004ActivityState(models.Model):
    """SCORM 2004 Activity State"""
    activity_id = models.CharField(max_length=255)
    learner = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    registration_id = models.UUIDField()
    
    # Activity state
    completion_status = models.CharField(max_length=20, choices=[
        ('completed', 'Completed'),
        ('incomplete', 'Incomplete'),
        ('not attempted', 'Not Attempted'),
        ('unknown', 'Unknown')
    ], default='not attempted')
    
    success_status = models.CharField(max_length=20, choices=[
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('unknown', 'Unknown')
    ], default='unknown')
    
    # Progress
    progress_measure = models.FloatField(null=True, blank=True)
    completion_threshold = models.FloatField(null=True, blank=True)
    
    # Score
    score_scaled = models.FloatField(null=True, blank=True)
    score_raw = models.FloatField(null=True, blank=True)
    score_min = models.FloatField(null=True, blank=True)
    score_max = models.FloatField(null=True, blank=True)
    
    # Time
    total_time = models.DurationField(null=True, blank=True)
    session_time = models.DurationField(null=True, blank=True)
    
    # Location and suspend data
    location = models.CharField(max_length=500, blank=True)
    suspend_data = models.TextField(blank=True)
    
    # Objectives
    objectives = models.JSONField(default=dict)
    
    # Interactions
    interactions = models.JSONField(default=dict)
    
    # Raw data
    raw_data = models.JSONField(default=dict)
    
    # Timestamps
    first_launch = models.DateTimeField(null=True, blank=True)
    last_launch = models.DateTimeField(null=True, blank=True)
    completion_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['activity_id', 'learner', 'registration_id']
        indexes = [
            models.Index(fields=['activity_id']),
            models.Index(fields=['learner']),
            models.Index(fields=['registration_id']),
        ]
    
    def __str__(self):
        return f"Activity State for {self.activity_id} - {self.learner.username}"
