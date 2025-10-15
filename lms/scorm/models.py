"""
SCORM Models
Handles SCORM packages, attempts, interactions, and tracking data
"""
import os
import json
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

import logging

logger = logging.getLogger(__name__)


class SCORMPackageType(models.TextChoices):
    """Different types of SCORM packages and authoring tools"""
    SCORM_12 = 'SCORM_12', _('SCORM 1.2')
    SCORM_2004 = 'SCORM_2004', _('SCORM 2004')
    XAPI = 'XAPI', _('xAPI/Tin Can')
    ARTICULATE_RISE = 'ARTICULATE_RISE', _('Articulate Rise 360')
    ARTICULATE_STORYLINE = 'ARTICULATE_STORYLINE', _('Articulate Storyline')
    ADOBE_CAPTIVATE = 'ADOBE_CAPTIVATE', _('Adobe Captivate')
    ISPRING = 'ISPRING', _('iSpring')
    LECTORA = 'LECTORA', _('Lectora')
    HTML5 = 'HTML5', _('Generic HTML5')
    AUTO = 'AUTO', _('Auto-detect')


class SCORMPackage(models.Model):
    """
    Represents a SCORM package uploaded to the system
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Basic Information
    title = models.CharField(max_length=500, help_text=_("Package title"))
    description = models.TextField(blank=True, help_text=_("Package description"))
    version = models.CharField(max_length=50, blank=True, help_text=_("Package version"))
    
    # Package Type
    package_type = models.CharField(
        max_length=50,
        choices=SCORMPackageType.choices,
        default=SCORMPackageType.AUTO,
        help_text=_("Type of SCORM package")
    )
    
    # File Storage
    package_file = models.FileField(
        upload_to='scorm/packages/%Y/%m/%d/',
        help_text=_("Original SCORM package ZIP file")
    )
    extracted_path = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Path to extracted package content in S3")
    )
    
    # Launch Information
    launch_file = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Main launch file (e.g., index.html, story.html)")
    )
    
    # Manifest Data (parsed from imsmanifest.xml)
    identifier = models.CharField(max_length=500, blank=True)
    manifest_data = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Parsed manifest data from imsmanifest.xml")
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='scorm_packages_created'
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_processed = models.BooleanField(
        default=False,
        help_text=_("Whether package has been extracted and processed")
    )
    processing_error = models.TextField(blank=True)
    
    # Size tracking
    file_size = models.BigIntegerField(default=0, help_text=_("File size in bytes"))
    
    # Course relationship
    topic = models.ForeignKey(
        'courses.Topic',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='scorm_packages',
        help_text=_("Associated course topic")
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = _('SCORM Package')
        verbose_name_plural = _('SCORM Packages')
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['is_active', 'is_processed']),
            models.Index(fields=['topic']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.get_package_type_display()})"
    
    def get_launch_url(self) -> str:
        """Get the full URL to launch this SCORM package"""
        if not self.is_processed or not self.launch_file:
            return ""
        
        # Construct S3 URL or local URL based on storage
        if self.extracted_path:
            base_url = default_storage.url(self.extracted_path)
            return f"{base_url}/{self.launch_file}"
        return ""
    
    def detect_package_type(self) -> str:
        """
        Auto-detect the package type from manifest or file structure
        Returns the detected package type
        """
        if self.package_type != SCORMPackageType.AUTO:
            return self.package_type
        
        # Check manifest data for SCORM version
        if self.manifest_data:
            schema_version = self.manifest_data.get('schemaversion', '')
            if '1.2' in schema_version:
                return SCORMPackageType.SCORM_12
            elif '2004' in schema_version or 'CAM' in schema_version:
                return SCORMPackageType.SCORM_2004
        
        # Check launch file name for authoring tool detection
        if self.launch_file:
            launch_lower = self.launch_file.lower()
            if 'story' in launch_lower:
                return SCORMPackageType.ARTICULATE_STORYLINE
            elif 'index_lms' in launch_lower or 'scormdriver' in launch_lower:
                return SCORMPackageType.ARTICULATE_RISE
            elif 'multiscreen' in launch_lower:
                return SCORMPackageType.ADOBE_CAPTIVATE
            elif 'presentation' in launch_lower:
                return SCORMPackageType.ISPRING
        
        # Default to SCORM 1.2
        return SCORMPackageType.SCORM_12
    
    def parse_manifest(self, manifest_path: str) -> Dict[str, Any]:
        """
        Parse imsmanifest.xml file and extract metadata
        """
        try:
            if default_storage.exists(manifest_path):
                with default_storage.open(manifest_path, 'r') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    
                    # Remove namespace for easier parsing
                    for elem in root.iter():
                        if '}' in elem.tag:
                            elem.tag = elem.tag.split('}', 1)[1]
                    
                    manifest_data = {
                        'identifier': root.get('identifier', ''),
                        'version': root.get('version', ''),
                        'schemaversion': '',
                        'resources': [],
                        'organizations': []
                    }
                    
                    # Get schema version
                    metadata = root.find('.//metadata')
                    if metadata is not None:
                        schema = metadata.find('.//schemaversion')
                        if schema is not None:
                            manifest_data['schemaversion'] = schema.text or ''
                    
                    # Get resources
                    resources = root.findall('.//resource')
                    for resource in resources:
                        manifest_data['resources'].append({
                            'identifier': resource.get('identifier', ''),
                            'type': resource.get('type', ''),
                            'href': resource.get('href', ''),
                        })
                    
                    # Get organizations/items for title
                    orgs = root.findall('.//organization')
                    for org in orgs:
                        items = org.findall('.//item')
                        for item in items:
                            title_elem = item.find('title')
                            manifest_data['organizations'].append({
                                'identifier': item.get('identifier', ''),
                                'title': title_elem.text if title_elem is not None else '',
                            })
                    
                    return manifest_data
        except Exception as e:
            logger.error(f"Error parsing manifest: {str(e)}")
        
        return {}
    
    def clean(self):
        """Validate the package"""
        super().clean()
        if self.file_size > 2 * 1024 * 1024 * 1024:  # 2GB limit
            raise ValidationError(_("Package file size cannot exceed 2GB"))


class SCORMAttempt(models.Model):
    """
    Represents a user's attempt at a SCORM package
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    package = models.ForeignKey(
        SCORMPackage,
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scorm_attempts'
    )
    topic = models.ForeignKey(
        'courses.Topic',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='scorm_attempts'
    )
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # SCORM Status
    lesson_status = models.CharField(
        max_length=50,
        default='not attempted',
        help_text=_("SCORM lesson status (not attempted, incomplete, completed, passed, failed, browsed)")
    )
    completion_status = models.CharField(
        max_length=50,
        default='unknown',
        help_text=_("SCORM 2004 completion status")
    )
    success_status = models.CharField(
        max_length=50,
        default='unknown',
        help_text=_("SCORM 2004 success status")
    )
    
    # Score
    score_raw = models.FloatField(null=True, blank=True, help_text=_("Raw score"))
    score_min = models.FloatField(null=True, blank=True, help_text=_("Minimum score"))
    score_max = models.FloatField(null=True, blank=True, help_text=_("Maximum score"))
    score_scaled = models.FloatField(null=True, blank=True, help_text=_("Scaled score (0-1)"))
    
    # Progress
    lesson_location = models.CharField(
        max_length=1000,
        blank=True,
        help_text=_("Bookmark/location in content")
    )
    suspend_data = models.TextField(
        blank=True,
        help_text=_("Suspend data for resuming")
    )
    
    # Time Tracking
    total_time = models.CharField(
        max_length=50,
        default='0000:00:00.00',
        help_text=_("Total time spent (SCORM timeinterval format)")
    )
    session_time = models.CharField(
        max_length=50,
        default='0000:00:00.00',
        help_text=_("Current session time")
    )
    
    # Additional Data
    learner_response = models.TextField(blank=True)
    learner_comments = models.TextField(blank=True)
    
    # Full CMI Data Storage
    cmi_data = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Complete CMI data object")
    )
    
    # Exit information
    exit_type = models.CharField(max_length=50, blank=True)
    
    # Metadata
    is_active = models.BooleanField(default=True)
    attempt_number = models.IntegerField(default=1)
    
    class Meta:
        ordering = ['-started_at']
        verbose_name = _('SCORM Attempt')
        verbose_name_plural = _('SCORM Attempts')
        indexes = [
            models.Index(fields=['user', 'package']),
            models.Index(fields=['started_at']),
            models.Index(fields=['lesson_status']),
            models.Index(fields=['topic']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.package.title} (Attempt {self.attempt_number})"
    
    def is_completed(self) -> bool:
        """Check if attempt is completed"""
        completed_statuses = ['completed', 'passed']
        return (
            self.lesson_status in completed_statuses or
            self.completion_status == 'completed' or
            self.success_status == 'passed'
        )
    
    def get_progress_percentage(self) -> int:
        """Calculate progress percentage"""
        if self.is_completed():
            return 100
        
        # Try to estimate from suspend data or interactions
        if self.interactions.exists():
            # Simple estimation based on number of interactions
            expected_interactions = 10  # This should be configurable
            actual_interactions = self.interactions.count()
            return min(int((actual_interactions / expected_interactions) * 100), 99)
        
        return 0
    
    def update_from_cmi(self, element: str, value: Any) -> None:
        """
        Update attempt data from CMI element
        """
        # Update specific fields based on CMI element
        cmi_map = {
            'cmi.core.lesson_status': 'lesson_status',
            'cmi.completion_status': 'completion_status',
            'cmi.success_status': 'success_status',
            'cmi.core.score.raw': 'score_raw',
            'cmi.score.raw': 'score_raw',
            'cmi.core.score.min': 'score_min',
            'cmi.score.min': 'score_min',
            'cmi.core.score.max': 'score_max',
            'cmi.score.max': 'score_max',
            'cmi.score.scaled': 'score_scaled',
            'cmi.core.lesson_location': 'lesson_location',
            'cmi.location': 'lesson_location',
            'cmi.suspend_data': 'suspend_data',
            'cmi.core.session_time': 'session_time',
            'cmi.session_time': 'session_time',
            'cmi.core.exit': 'exit_type',
            'cmi.exit': 'exit_type',
        }
        
        # Update model field if mapped
        if element in cmi_map:
            field_name = cmi_map[element]
            try:
                # Convert value to appropriate type
                if 'score' in field_name and value:
                    value = float(value)
                setattr(self, field_name, value)
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not convert value for {element}: {e}")
        
        # Always store in cmi_data
        if not self.cmi_data:
            self.cmi_data = {}
        self.cmi_data[element] = value
        
        # Check if completed
        if self.is_completed() and not self.completed_at:
            self.completed_at = timezone.now()


class SCORMInteraction(models.Model):
    """
    Tracks detailed interactions within a SCORM package
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    attempt = models.ForeignKey(
        SCORMAttempt,
        on_delete=models.CASCADE,
        related_name='interactions'
    )
    
    # Interaction Details
    interaction_id = models.CharField(max_length=255)
    interaction_type = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("true-false, choice, fill-in, long-fill-in, matching, performance, sequencing, likert, numeric, other")
    )
    
    # Objectives
    objectives = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Associated learning objectives")
    )
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Response and Result
    learner_response = models.TextField(blank=True)
    result = models.CharField(max_length=50, blank=True)
    correct_response = models.TextField(blank=True)
    
    # Weighting and Latency
    weighting = models.FloatField(null=True, blank=True)
    latency = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("Time taken to complete interaction")
    )
    
    # Description
    description = models.TextField(blank=True)
    
    # Raw interaction data
    raw_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['timestamp']
        verbose_name = _('SCORM Interaction')
        verbose_name_plural = _('SCORM Interactions')
        indexes = [
            models.Index(fields=['attempt', 'timestamp']),
            models.Index(fields=['interaction_id']),
        ]
    
    def __str__(self):
        return f"Interaction {self.interaction_id} - {self.attempt}"


class SCORMObjective(models.Model):
    """
    Tracks learning objectives within SCORM content
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    attempt = models.ForeignKey(
        SCORMAttempt,
        on_delete=models.CASCADE,
        related_name='objectives'
    )
    
    # Objective Details
    objective_id = models.CharField(max_length=255)
    
    # Status
    status = models.CharField(
        max_length=50,
        default='unknown',
        help_text=_("passed, failed, completed, incomplete, browsed, not attempted, unknown")
    )
    success_status = models.CharField(max_length=50, blank=True)
    completion_status = models.CharField(max_length=50, blank=True)
    
    # Score
    score_raw = models.FloatField(null=True, blank=True)
    score_min = models.FloatField(null=True, blank=True)
    score_max = models.FloatField(null=True, blank=True)
    score_scaled = models.FloatField(null=True, blank=True)
    
    # Description
    description = models.TextField(blank=True)
    
    # Progress measure (SCORM 2004)
    progress_measure = models.FloatField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
        verbose_name = _('SCORM Objective')
        verbose_name_plural = _('SCORM Objectives')
        indexes = [
            models.Index(fields=['attempt', 'objective_id']),
        ]
    
    def __str__(self):
        return f"Objective {self.objective_id} - {self.attempt}"


class SCORMEvent(models.Model):
    """
    Tracks all SCORM API calls and events for debugging and analytics
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    attempt = models.ForeignKey(
        SCORMAttempt,
        on_delete=models.CASCADE,
        related_name='events',
        null=True,
        blank=True
    )
    
    # Event Details
    event_type = models.CharField(
        max_length=50,
        help_text=_("Initialize, SetValue, GetValue, Commit, Terminate, etc.")
    )
    element = models.CharField(max_length=500, blank=True)
    value = models.TextField(blank=True)
    
    # Result
    result = models.CharField(max_length=50, default='true')
    error_code = models.CharField(max_length=10, default='0')
    error_message = models.TextField(blank=True)
    
    # Timing
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Session info
    session_id = models.UUIDField(null=True, blank=True)
    
    # Raw request data
    request_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['timestamp']
        verbose_name = _('SCORM Event')
        verbose_name_plural = _('SCORM Events')
        indexes = [
            models.Index(fields=['attempt', 'timestamp']),
            models.Index(fields=['event_type']),
            models.Index(fields=['session_id']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.timestamp}"

