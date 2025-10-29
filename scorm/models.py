"""
SCORM Package models for LMS
"""
from django.db import models
from django.core.exceptions import ValidationError
import json
import logging

# Use Django's JSONField if available (Django 3.1+), otherwise use postgres JSONField
try:
    from django.db.models import JSONField
except ImportError:
    try:
        from django.contrib.postgres.fields import JSONField
    except ImportError:
        # Fallback - this shouldn't happen in modern Django
        JSONField = models.TextField  # Will need manual JSON handling

logger = logging.getLogger(__name__)


class ScormPackage(models.Model):
    """Model for storing SCORM package metadata and processing status"""
    
    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]
    
    SCORM_VERSION_CHOICES = [
        ('1.2', 'SCORM 1.2'),
        ('2004', 'SCORM 2004'),
    ]
    
    title = models.CharField(max_length=255, help_text="Title extracted from manifest")
    version = models.CharField(
        max_length=16, 
        choices=SCORM_VERSION_CHOICES,
        null=True,
        blank=True,
        help_text="SCORM version (1.2 or 2004)"
    )
    
    # File storage
    package_zip = models.FileField(
        upload_to='scorm_packages/zips/',
        null=True,
        blank=True,
        help_text="Original uploaded ZIP file"
    )
    extracted_path = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="S3 path to extracted package directory"
    )
    
    # Manifest data stored as JSON
    manifest_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Parsed manifest data (organizations, resources, metadata)"
    )
    
    # Processing status
    processing_status = models.CharField(
        max_length=32,
        choices=PROCESSING_STATUS_CHOICES,
        default='pending',
        help_text="Package processing status"
    )
    processing_error = models.TextField(
        blank=True,
        null=True,
        help_text="Error message if processing failed"
    )
    
    # Metadata
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_scorm_packages',
        help_text="User who uploaded this package"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'scorm'
        ordering = ['-created_at']
        verbose_name = 'SCORM Package'
        verbose_name_plural = 'SCORM Packages'
    
    def __str__(self):
        status = self.get_processing_status_display()
        version = self.version or 'Unknown'
        return f"{self.title} ({version}) - {status}"
    
    def get_entry_point(self):
        """Attempt to extract entry point (launch file) from manifest data"""
        try:
            orgs = self.manifest_data.get("organizations", [])
            if not orgs:
                return None
            
            # Get first organization's first item
            first_org = orgs[0]
            items = first_org.get("items", [])
            if not items:
                return None
            
            first_item = items[0]
            identifierref = first_item.get("identifierref")
            
            if not identifierref:
                return None
            
            # Find resource with this identifierref
            resources = self.manifest_data.get("resources", [])
            for resource in resources:
                if resource.get("identifier") == identifierref:
                    href = resource.get("href", "")
                    return href
            
            return None
        except Exception as e:
            logger.error(f"Error extracting entry point for SCORM package {self.id}: {e}")
            return None
    
    def validate_package(self):
        """Validate that package has required manifest structure"""
        if not self.manifest_data:
            raise ValidationError("Manifest data is required")
        
        if not self.version:
            raise ValidationError("SCORM version must be set")
        
        # Check for basic manifest structure
        if "organizations" not in self.manifest_data:
            raise ValidationError("Manifest must contain organizations")
        
        if "resources" not in self.manifest_data:
            raise ValidationError("Manifest must contain resources")
    
    def clean(self):
        """Run validation on save"""
        super().clean()
        if self.processing_status == 'ready':
            try:
                self.validate_package()
            except ValidationError as e:
                logger.warning(f"Package {self.id} validation failed: {e}")
                # Don't raise - allow saving but log warning

